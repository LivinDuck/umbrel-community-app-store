# frozen_string_literal: true
require 'net/http'
require 'json'
require 'digest'
require 'bencode'

module ShelfarrTorboxCache
  LEGACY_CONFIG = File.join(__dir__, 'credentials.json')
  CONFIG = File.file?(LEGACY_CONFIG) ? LEGACY_CONFIG : '/rails/storage/custom/torbox-cache.json'
  class LookupError < StandardError; end

  def self.config
    JSON.parse(File.read(ENV.fetch('SHELFARR_TORBOX_CACHE_CONFIG', CONFIG)))
  end

  # No torrent is submitted by these lookups. Response sizes and IO are bounded.
  def self.get(uri, headers = {})
    body = +''.b
    response = nil
    Net::HTTP.start(uri.host, uri.port, use_ssl: uri.scheme == 'https',
      open_timeout: 2, read_timeout: 3, write_timeout: 3) do |http|
      http.max_retries = 0
      http.request(Net::HTTP::Get.new(uri, headers)) do |res|
        response = res
        res.read_body do |chunk|
          body << chunk
          raise LookupError, 'Response too large' if body.bytesize > 2_000_000
        end
      end
    end
    [response, body]
  end

  def self.normalize_hash(value)
    text = value.to_s.downcase
    text if text.match?(/\A[0-9a-f]{40}\z/)
  end

  class HashResolver
    def call(result)
      url = result.magnet_url.presence || result.download_url.to_s
      return MagnetLink.info_hash(url) if url.start_with?('magnet:')
      return unless result.source == SearchResult::SOURCE_JACKETT

      # Only resolve the configured Jackett download endpoint; never follow
      # arbitrary provider links or send Jackett credentials to another host.
      base = URI(SettingsService.get(:jackett_url))
      uri = URI(url)
      return unless allowed?(uri, base)
      key = "torbox-torrent-hash/v1/#{Digest::SHA256.hexdigest(url)}"
      Rails.cache.fetch(key, expires_in: 6.hours, skip_nil: true) do
        resolve(uri, base)
      end
    rescue StandardError
      nil
    end

    def allowed?(uri, base)
      %w[http https].include?(uri.scheme) &&
        [uri.scheme, uri.host, uri.port] == [base.scheme, base.host, base.port] &&
        uri.path.start_with?("#{base.path.sub(%r{/\z}, '')}/dl/")
    end

    def resolve(uri, base)
      3.times do
        response, body = ShelfarrTorboxCache.get(uri)
        if response.is_a?(Net::HTTPRedirection)
          target = response['location'].to_s
          return MagnetLink.info_hash(target) if target.start_with?('magnet:')
          uri = URI.join(uri.to_s, target)
          return unless allowed?(uri, base)
        elsif response.is_a?(Net::HTTPSuccess)
          return MagnetLink.info_hash(body.strip) if body.strip.start_with?('magnet:')
          parsed = BEncode.load(body)
          return unless parsed.is_a?(Hash) && parsed['info'].is_a?(Hash)
          return Digest::SHA1.hexdigest(parsed['info'].bencode)
        else
          return
        end
      end
      nil
    end
  end

  class Client
    def initialize(key)
      @key = key
    end

    def cached_hashes(hashes)
      return [] if hashes.empty?
      uri = URI('https://api.torbox.app/v1/api/torrents/checkcached')
      uri.query = URI.encode_www_form(hash: hashes.uniq.join(','), format: 'list', list_files: 'false')
      response, body = ShelfarrTorboxCache.get(uri, 'Authorization' => "Bearer #{@key}")
      raise LookupError, 'Cache lookup failed' unless response.is_a?(Net::HTTPSuccess)
      payload = JSON.parse(body)
      raise LookupError, 'Invalid cache response' unless payload['success'] == true && payload['data'].is_a?(Array)
      payload['data'].filter_map { |item| ShelfarrTorboxCache.normalize_hash(item['hash']) if item.is_a?(Hash) } & hashes
    end
  end

  class Preference
    def initialize(config: ShelfarrTorboxCache.config, resolver: HashResolver.new, client: nil)
      @config, @resolver = config, resolver
      @client = client || Client.new(config.fetch('api_key'))
    end

    def cached_ids(results)
      configured = DownloadClient.torrent_clients.enabled.by_priority.to_a
      id = @config.fetch('download_client_id').to_i
      return [] unless configured.any? { |c| c.id == id }
      candidates = results.select do |r|
        route = DownloadRoutingRule.routed_client_for(r) || configured.first
        r.torrent? && !r.direct_download? && !r.usenet? && r.downloadable? && route&.id == id
      end
      # Check best-ranked candidates in bounded batches. Stop as soon as a
      # batch contains cached matches; existing ranking breaks ties.
      deadline = Process.clock_gettime(Process::CLOCK_MONOTONIC) + 20
      candidates.first(30).each_slice(10) do |batch|
        hashes = {}
        batch.each do |r|
          break if Process.clock_gettime(Process::CLOCK_MONOTONIC) >= deadline
          hash = ShelfarrTorboxCache.normalize_hash(@resolver.call(r))
          hashes[r.id] = hash if hash
        end
        cached = @client.cached_hashes(hashes.values)
        ids = hashes.filter_map { |result_id, hash| result_id if cached.include?(hash) }
        return ids if ids.any?
        break if Process.clock_gettime(Process::CLOCK_MONOTONIC) >= deadline
      end
      []
    rescue StandardError => e
      Rails.logger.warn("[TorboxCache] Lookup unavailable (#{e.class}); using normal selection")
      []
    end
  end

  module Selection
    private

    def find_matching_results
      results = super
      @torbox_cached_ids = []
      return results unless @request.book.audiobook?
      @torbox_cached_ids = Preference.new.cached_ids(results)
      return results if @torbox_cached_ids.empty?

      # Keep non-torrent download preferences in place. Rank cached results
      # first within the torrent slots, retaining the original order in ties.
      torrents = results.select { |r| r.torrent? && !r.direct_download? && !r.usenet? }
      cached, other = torrents.partition { |r| @torbox_cached_ids.include?(r.id) }
      ordered = (cached + other).each
      Rails.logger.info("[TorboxCache] Prioritizing #{cached.size} cached torrent(s) for request ##{@request.id}")
      results.map { |r| torrents.include?(r) ? ordered.next : r }
    rescue StandardError => e
      @torbox_cached_ids = []
      Rails.logger.warn("[TorboxCache] Preference unavailable (#{e.class}); using normal selection")
      results
    end

    def meets_seeder_threshold?(result)
      return true if Array(@torbox_cached_ids).include?(result.id)
      super
    end
  end
end

Rails.application.config.to_prepare do
  AutoSelectService.prepend(ShelfarrTorboxCache::Selection) unless AutoSelectService < ShelfarrTorboxCache::Selection
end
