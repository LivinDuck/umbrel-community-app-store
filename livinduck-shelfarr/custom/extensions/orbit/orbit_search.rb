# frozen_string_literal: true
# Shelfarr integration for BookOrbit v3.3.0. See NOTICE and the source download.
require 'net/http'
require 'json'
require 'digest'
require 'securerandom'
module OrbitSearch
  ROOT = File.expand_path(__dir__)
  class Error < StandardError; end
  class Client
    BASE = URI(ENV.fetch('BOOKORBIT_URL', 'http://livinduck-bookorbit_server_1:3000/api/v1/'))
    def initialize
      @config = JSON.parse(File.read(ENV.fetch('ORBIT_SEARCH_CONFIG', (File.file?(File.join(ROOT, 'credentials.json')) ? File.join(ROOT, 'credentials.json') : '/rails/storage/custom/orbit.json'))))
    end
    def token
      Rails.cache.fetch('orbit-search/access-token/v1', expires_in: 5.minutes) do
        uri = URI.join(BASE.to_s, 'auth/login')
        req = Net::HTTP::Post.new(uri); req['Content-Type'] = 'application/json'
        req.body = @config.slice('username', 'password').to_json
        response = connection(uri).request(req)
        raise Error, 'BookOrbit login failed' unless response.is_a?(Net::HTTPSuccess)
        JSON.parse(response.body).fetch('accessToken')
      end
    end
    def connection(uri)
      Net::HTTP.new(uri.host, uri.port, nil).tap { |h| h.open_timeout = 5; h.read_timeout = 90 }
    end
    def get(path, &block)
      raise Error, 'Invalid endpoint' unless path.match?(/\Ametadata-fetch\/(providers|stream)(\?|\z)/)
      uri = URI.join(BASE.to_s, path)
      2.times do |attempt|
        req = Net::HTTP::Get.new(uri); req['Authorization'] = "Bearer #{token}"
        retry_auth = false
        connection(uri).request(req) do |response|
          if response.code == '401' && attempt.zero?
            Rails.cache.delete('orbit-search/access-token/v1'); retry_auth = true
          elsif !response.is_a?(Net::HTTPSuccess)
            raise Error, "BookOrbit returned HTTP #{response.code}"
          elsif block
            response.read_body(&block)
          else
            return JSON.parse(response.body)
          end
        end
        return unless retry_auth
      end
    rescue Error
      raise
    rescue StandardError => e
      # Never expose upstream response bodies, URLs with credentials, or tokens.
      raise Error, "BookOrbit connection failed (#{e.class.name})"
    end
  end
  def self.tokenize(value)
    value.to_s.downcase.unicode_normalize(:nfkd).gsub(/[\u0300-\u036f]/,'').gsub(/[^\p{L}\p{N}]/,'')
  end
  def self.fnv(value)
    value.codepoints.reduce(0x811c9dc5) { |h,c| ((h ^ c) * 0x01000193) & 0xffffffff }.to_s(16)
  end
  def self.js_length(value) = value.encode('UTF-16LE').bytesize / 2
  def self.bound(value)
    return value if js_length(value) <= 160
    value.encode('UTF-16LE').byteslice(0,320).force_encoding('UTF-16LE').encode('UTF-8', invalid: :replace) + '~' + fnv(value)
  end
  def self.work_key(candidate, medium)
    title = (candidate['displayTitle'] || candidate['title']).to_s
    t = tokenize(title); t = 'x' + fnv(title.strip.downcase) if t.empty?
    a = tokenize(Array(candidate['authors']).first)
    key = "work:#{t}:#{a}:#{medium}"
    js_length(key) <= 500 ? key : "work:#{bound(t)}:#{bound(a)}:#{medium}"
  end
  def self.identity(candidate, medium) = Digest::SHA256.hexdigest(work_key(candidate, medium))
  def self.book_type(medium) = {'ebook'=>'ebook','audiobook'=>'audiobook','comic'=>'comicbook'}.fetch(medium)
  def self.store(user, candidate, medium)
    token = SecureRandom.hex(24)
    Rails.cache.write("orbit-search/candidate/#{user.id}/#{token}", {candidate:candidate, medium:medium}, expires_in:1.hour)
    token
  end
  def self.fetch(user, token)
    raise Error, 'Search result expired. Search again.' unless token.to_s.match?(/\A[0-9a-f]{48}\z/)
    Rails.cache.read("orbit-search/candidate/#{user.id}/#{token}") || raise(Error, 'Search result expired. Search again.')
  end
  def self.metadata(c, medium, cover=nil)
    {title:c['displayTitle'] || c['title'], author:Array(c['authors']).join(', '), cover_url:cover || c['coverUrl'],
     year:c['publishedYear'], description:c['description'], publisher:c['publisher'], series:c['seriesName'],
     series_position:c['seriesIndex'], content_kind:medium == 'comic' ? 'graphic' : 'book'}.compact
  end
  # An existing record can predate this integration. Strong identifiers first,
  # otherwise an exact normalized title AND author, within the requested medium.
  def self.existing(c, medium)
    type = book_type(medium)
    found = Book.find_by(bookorbit_id:identity(c,medium),book_type:type)
    return found if found
    ids = [c['isbn13'],c['isbn10']].compact_blank
    matches = ids.empty? ? [] : Book.where(book_type:type,isbn:ids).limit(2).to_a
    return matches.first if matches.one?
    title = (c['displayTitle'] || c['title']).to_s
    titles = [title,c['title']].compact.uniq.map(&:downcase)
    Book.where(book_type:type).where('LOWER(title) IN (?)',titles).limit(50).detect do |book|
      tokenize(book.author) == tokenize(Array(c['authors']).join(', ')) && tokenize(book.title) == tokenize(title)
    end
  end
  module BooksClass
    def find_by_work_id(id, book_type:)
      return find_by(bookorbit_id:id.delete_prefix('bookorbit:'),book_type:book_type) if id.to_s.start_with?('bookorbit:')
      super
    end
    def find_or_initialize_by_work_id(id, book_type:)
      return find_or_initialize_by(bookorbit_id:id.delete_prefix('bookorbit:'),book_type:book_type) if id.to_s.start_with?('bookorbit:')
      super
    end
    def preload_by_work_ids(ids)
      orbit, rest = Array(ids).partition { |id| id.to_s.start_with?('bookorbit:') }
      lookup = Hash.new { |h,k| h[k] = {} }.merge(super(rest))
      where(bookorbit_id:orbit.map { |id| id.delete_prefix('bookorbit:') }).includes(:requests).each do |book|
        work_ids_for(book).each { |id| lookup[id][book.book_type] = book }
      end if orbit.any?
      lookup
    end
    def work_ids_for(book)
      super + (book.bookorbit_id.present? ? ["bookorbit:#{book.bookorbit_id}"] : [])
    end
  end
  module BooksInstance
    def assign_work_id(id)
      return self.bookorbit_id ||= id.delete_prefix('bookorbit:') if id.to_s.start_with?('bookorbit:')
      super
    end
    def unified_work_id = bookorbit_id.present? ? "bookorbit:#{bookorbit_id}" : super
    def metadata_source_name = bookorbit_id.present? ? 'BookOrbit' : super
    def metadata_source_url
      return super unless bookorbit_id.present?
      data = JSON.parse(bookorbit_metadata.presence || '{}')
      url = data.dig('candidate','sourceUrl')
      url.to_s.match?(/\Ahttps?:\/\//) ? url : nil
    rescue JSON::ParserError
      nil
    end
  end
  module Lookup
    def normalize_work_ids(ids)
      orbit, rest = Array(ids).partition { |id| id.to_s.match?(/\Abookorbit:[0-9a-f]{64}\z/) }
      orbit.first(1) + super(rest)
    end
    def call(ids, **options)
      orbit = Array(ids).find { |id| id.to_s.start_with?('bookorbit:') }
      return super unless orbit
      book = Book.find_by(bookorbit_id:orbit.delete_prefix('bookorbit:'))
      data = JSON.parse(book&.bookorbit_metadata.presence || '{}')
      data['metadata'].to_h.symbolize_keys
    end
  end
  module Creation
    private
    def find_or_create_book_for_source(type, input:, existing_books_lookup:)
      book = super
      if input.work_id.start_with?('bookorbit:') && input.metadata_attrs[:orbit_payload]
        payload = input.metadata_attrs[:orbit_payload]
        book.bookorbit_metadata = payload.to_json
        book.isbn = payload['isbn'].presence
        book.cover_url = payload.dig('metadata', :cover_url) || payload.dig('metadata', 'cover_url') || book.cover_url
        book.narrator = Array(payload.dig('candidate','narrators')).map { |v| v.is_a?(Hash) ? v['name'] : v }.compact.join(', ').presence || book.narrator
        book.save!
      end
      book
    end
  end
  module SearchPage
    def index
      render inline:File.read(File.join(OrbitSearch::ROOT,'views/index.html.erb')), layout:'application'
    end
  end
end
Rails.application.config.to_prepare do
  # BookOrbit creates requests inside a transaction, while Solid Queue uses a
  # separate database. Workers must not see a job before its request is committed.
  # Rails also discards the deferred enqueue when the transaction rolls back.
  SearchJob.enqueue_after_transaction_commit = true
  Book.singleton_class.prepend(OrbitSearch::BooksClass) unless Book.singleton_class < OrbitSearch::BooksClass
  Book.prepend(OrbitSearch::BooksInstance) unless Book < OrbitSearch::BooksInstance
  BookMetadataLookupService.singleton_class.prepend(OrbitSearch::Lookup) unless BookMetadataLookupService.singleton_class < OrbitSearch::Lookup
  RequestCreationService.prepend(OrbitSearch::Creation) unless RequestCreationService < OrbitSearch::Creation
  SearchController.prepend(OrbitSearch::SearchPage) unless SearchController < OrbitSearch::SearchPage
  load File.join(OrbitSearch::ROOT,'controller.inc') unless defined?(OrbitSearchController)
end
Rails.application.routes.prepend do
  get '/search/orbit/providers', to:'orbit_search#providers'
  get '/search/orbit/stream', to:'orbit_search#stream'
  post '/search/orbit/availability', to:'orbit_search#availability'
  post '/search/orbit/request', to:'orbit_search#create'
  get '/search/orbit/app.js', to:'orbit_search#javascript'
  get '/search/orbit/style.css', to:'orbit_search#stylesheet'
  get '/search/orbit/source', to:'orbit_search#source'
end
