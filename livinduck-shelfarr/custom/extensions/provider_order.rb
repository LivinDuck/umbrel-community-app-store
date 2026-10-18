# frozen_string_literal: true
require "digest"

# Aggregator clusters are emitted in first-occurrence order, so retaining that
# sequence preserves provider relevance while keeping deduplication/filtering.
module ShelfarrProviderOrder
  SOURCE_DIGESTS = {
    "app/services/metadata_service.rb" => "f9c0766443178991eb2c9d9cd6d209765409a766a3c4ad70dac10b8795be6333",
    "app/services/metadata_search/aggregator.rb" => "0df4c8717334063bb85837d3858bd85d919698fedd0024bf20a2bdd44833f189"
  }.freeze

  private

  def sort_candidates(candidates, requested_content_kind: nil)
    candidates
  end
end

Rails.application.config.to_prepare do
  if ShelfarrProviderOrder::SOURCE_DIGESTS.all? { |path, digest| Digest::SHA256.file(Rails.root.join(path)).hexdigest == digest }
    MetadataService.singleton_class.prepend(ShelfarrProviderOrder) unless MetadataService.singleton_class < ShelfarrProviderOrder
  else
    Rails.logger.warn("[ShelfarrProviderOrder] Upstream source changed; provider-order extension skipped pending review")
  end
end
