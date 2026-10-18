# frozen_string_literal: true

# Local compatibility-checked extension for Shelfarr 2026.10.05.1.
# Mounted read-only into config/initializers; see README.md before upgrades.
require "digest"
require "time"

module ShelfarrGoogleBooksResilience
  SOURCE_DIGESTS = {
    "app/services/google_books_client.rb" => "de94e2addd66c8dbe1d928b9e677159a02cd00558149ad904752d4e153e02297",
    "app/models/metadata_provider_status.rb" => "17c1a443df1482a6b06cbf3dec4a50f1c9ecbd69fbac41ba39222e00ff44f328"
  }.freeze
  MAX_ATTEMPTS = 3
  TRANSIENT_STATUSES = [500, 502, 503, 504].freeze

  module Client
    def search(...)
      with_google_books_retry { super }
    end

    def book(...)
      with_google_books_retry { super }
    end

    private

    def handle_response(response, &block)
      if TRANSIENT_STATUSES.include?(response.status)
        error = GoogleBooksClient::TransientError.new("Google Books temporarily unavailable (HTTP #{response.status})")
        error.retry_at = google_books_retry_at(response.headers["retry-after"])
        raise error
      end

      super
    end

    def with_google_books_retry
      attempts = 0
      begin
        attempts += 1
        yield
      rescue GoogleBooksClient::TransientError => error
        raise if attempts >= MAX_ATTEMPTS

        delay = (0.5 * (2**(attempts - 1))) + rand * 0.25
        delay = [delay, error.retry_at - Time.current].max if error.retry_at
        # Do not hold a search open for a long Retry-After. The provider status
        # retains that deadline and the next search can try after it expires.
        raise if delay > 2.0

        Rails.logger.info("[GoogleBooksResilience] Transient failure; retry #{attempts + 1}/#{MAX_ATTEMPTS}")
        sleep(delay)
        retry
      end
    end

    def google_books_retry_at(value)
      return if value.to_s.strip.empty?

      value = value.to_s.strip
      value.match?(/\A\d+\z/) ? Time.current + value.to_i : Time.httpdate(value)
    rescue ArgumentError
      nil
    end
  end

  module ProviderStatus
    private

    def backoff_until_for(error)
      return super unless provider == "google_books" && error.is_a?(GoogleBooksClient::TransientError)

      # One difficult query must not suppress unrelated searches. Only open
      # the global circuit after a second consecutive exhausted operation.
      return error.retry_at if failure_count.to_i.zero?

      deadline = Time.current + 30 * (2**(failure_count.to_i - 1).clamp(0, 2))
      [deadline, error.retry_at].compact.max
    end
  end
end

Rails.application.config.to_prepare do
  compatible = ShelfarrGoogleBooksResilience::SOURCE_DIGESTS.all? do |relative_path, digest|
    path = Rails.root.join(relative_path)
    path.file? && Digest::SHA256.file(path).hexdigest == digest
  end

  if compatible
    class GoogleBooksClient::TransientError < GoogleBooksClient::Error
      attr_accessor :retry_at
    end

    GoogleBooksClient.singleton_class.prepend(ShelfarrGoogleBooksResilience::Client) unless
      GoogleBooksClient.singleton_class < ShelfarrGoogleBooksResilience::Client
    MetadataProviderStatus.prepend(ShelfarrGoogleBooksResilience::ProviderStatus) unless
      MetadataProviderStatus < ShelfarrGoogleBooksResilience::ProviderStatus
  else
    Rails.logger.warn("[GoogleBooksResilience] Source changed: local extension disabled; review before enabling on this Shelfarr version")
  end
end
