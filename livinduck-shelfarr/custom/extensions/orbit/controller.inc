class OrbitSearchController < ApplicationController
  include ActionController::Live
  rescue_from OrbitSearch::Error do |error|
    render json:{error:error.message}, status: :unprocessable_entity
  end
  def providers
    response.headers['Cache-Control'] = 'no-store'
    render json:OrbitSearch::Client.new.get('metadata-fetch/providers')
  end
  def stream
    medium = params[:mediaKind].to_s
    raise OrbitSearch::Error, 'Choose a supported format' unless %w[ebook audiobook comic].include?(medium)
    query = params.permit(:title,:author,:isbn,:providers).to_h.transform_values { |v| v.to_s.first(1000) }.merge('mediaKind'=>medium)
    raise OrbitSearch::Error, 'Enter a title, author, or ISBN' if query.values_at('title','author','isbn').all?(&:blank?)
    user = Current.user
    response.headers['Content-Type'] = 'text/event-stream; charset=utf-8'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Accel-Buffering'] = 'no'
    buffer = +''
    OrbitSearch::Client.new.get('metadata-fetch/stream?' + URI.encode_www_form(query)) do |chunk|
      buffer << chunk
      raise OrbitSearch::Error, 'Search response too large' if buffer.bytesize > 2.megabytes
      while (index = buffer.index("\n\n"))
        event = buffer.slice!(0,index+2)
        lines = event.lines
        data = lines.find { |line| line.start_with?('data:') }
        name = lines.find { |line| line.start_with?('event:') }&.delete_prefix('event:')&.strip
        if data && (name.blank? || name == 'message')
          candidate = JSON.parse(data.delete_prefix('data:'))
          if candidate.is_a?(Hash) && candidate['provider'] && candidate['providerId']
            candidate['_token'] = OrbitSearch.store(user,candidate,medium)
            event = "data: #{candidate.to_json}\n\n"
          end
        end
        response.stream.write(event)
      end
    end
  rescue OrbitSearch::Error => error
    if response.committed?
      response.stream.write("event: orbit-error\ndata: #{ {message:error.message}.to_json }\n\n")
    else
      render json:{error:error.message}, status: :bad_gateway
    end
  rescue ActionController::Live::ClientDisconnected, IOError
    # Browser cancelled the search.
  ensure
    response.stream.close
  end
  def availability
    tokens = Array(params[:tokens]).first(100)
    results = tokens.to_h do |token|
      stored = OrbitSearch.fetch(Current.user, token)
      book = OrbitSearch.existing(stored[:candidate],stored[:medium])
      req = book&.requests&.open&.first
      # Preserve Shelfarr's visibility rules for request links.
      visible = req && (Current.user.admin? || req.user_id == Current.user.id)
      [token, {ownedBookId:book&.acquired? ? book.id : nil, existingRequestId:visible ? req.id : nil, existingRequestStatus:visible ? req.status : nil, alreadySubscribed:false}]
    end
    render json:results
  end
  def create
    stored = OrbitSearch.fetch(Current.user, params[:token]); candidate = stored[:candidate]; medium = stored[:medium]
    key = OrbitSearch.work_key(candidate, medium)
    members = ([params[:token]] + Array(params[:tokens]).first(64)).uniq.map do |token|
      member = OrbitSearch.fetch(Current.user, token)
      raise OrbitSearch::Error, 'Mismatched search results' unless member[:medium] == medium && OrbitSearch.work_key(member[:candidate], medium) == key
      member[:candidate]
    end
    cover = params[:cover].presence
    raise OrbitSearch::Error, 'Invalid cover choice' if cover && !members.any? { |c| c['coverUrl'] == cover }
    isbn = params[:isbn].presence
    # ISBN choices must be canonical editions actually supplied by this group.
    valid_isbns = members.flat_map { |c| [canonical_isbn(c['isbn10']),canonical_isbn(c['isbn13'])] }.compact
    raise OrbitSearch::Error, 'Invalid edition choice' if isbn && !valid_isbns.include?(isbn)
    identity = OrbitSearch.identity(candidate,medium)
    attrs = OrbitSearch.metadata(candidate,medium,cover)
    attrs[:orbit_payload] = {'candidate'=>candidate.except('_token'), 'members'=>members.map { |c| c.except('_token') },'metadata'=>attrs.dup,'isbn'=>isbn,'medium'=>medium}
    result = nil
    Book.transaction do
      existing = members.filter_map { |c| OrbitSearch.existing(c,medium) }.uniq(&:id)
      raise OrbitSearch::Error, 'These editions match different existing records. Select a different edition.' if existing.size > 1
      if (book = existing.first)
        if book.acquired? || book.requests.open.exists?
          raise OrbitSearch::Error, book.acquired? ? 'This format is already in your library.' : 'This format already has an active request.'
        end
        book.update!(bookorbit_id:identity)
      end
      result = RequestCreationService.call(user:Current.user,work_id:"bookorbit:#{identity}",book_types:[OrbitSearch.book_type(medium)],metadata_attrs:attrs,notes:params[:notes].to_s.first(2000),language:params[:language].to_s.first(12).presence)
      raise ActiveRecord::Rollback unless result.success?
    end
    if result.success?
      render json:{url:request_path(result.created_requests.first),warnings:result.warnings}
    else
      render json:{errors:result.errors}, status: :unprocessable_entity
    end
  end
  def javascript = send_file(File.join(OrbitSearch::ROOT,'public/search.js'), type:'application/javascript', disposition:'inline')
  def stylesheet = send_file(File.join(OrbitSearch::ROOT,'public/search.css'), type:'text/css', disposition:'inline')
  def source = send_file(File.join(OrbitSearch::ROOT,'public/source.tar.gz'), type:'application/gzip', disposition:'attachment', filename:'shelfarr-bookorbit-search-source.tar.gz')
  private
  def canonical_isbn(value)
    isbn = value.to_s.gsub(/[^0-9Xx]/,'').upcase
    if isbn.match?(/\A97[89]\d{10}\z/)
      return isbn if isbn.chars.each_with_index.sum { |c,i| c.to_i * (i.even? ? 1 : 3) } % 10 == 0
    end
    return unless isbn.match?(/\A\d{9}[\dX]\z/)
    return unless isbn.chars.each_with_index.sum { |c,i| (c == 'X' ? 10 : c.to_i) * (10-i) } % 11 == 0
    body = '978' + isbn.first(9)
    body + ((10 - body.chars.each_with_index.sum { |c,i| c.to_i * (i.even? ? 1 : 3) } % 10) % 10).to_s
  end
end
