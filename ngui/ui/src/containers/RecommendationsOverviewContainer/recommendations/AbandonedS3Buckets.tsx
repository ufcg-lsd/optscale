import { FormattedMessage } from "react-intl";
import FormattedMoney from "components/FormattedMoney";
import RecommendationListItemResourceLabel from "components/RecommendationListItemResourceLabel";
import AbandonedS3BucketsModal from "components/SideModalManager/SideModals/recommendations/AbandonedS3BucketsModal";
import TextWithDataTestId from "components/TextWithDataTestId";
import { AWS_S3 } from "hooks/useRecommendationServices";
import { detectedAt, poolOwner, possibleMonthlySavings, resource, resourceLocation } from "utils/columns";
import { AWS_CNR, FORMATTED_MONEY_TYPES } from "utils/constants";
import BaseRecommendation, { CATEGORY } from "./BaseRecommendation";

const columns = [
  resource({
    headerDataTestId: "lbl_s3_abandoned_buckets_resource"
  }),
  resourceLocation({
    headerDataTestId: "lbl_s3_abandoned_buckets_location",
    typeAccessor: "cloud_type"
  }),
  poolOwner({
    headerDataTestId: "lbl_s3_abandoned_buckets_pool_owner",
    id: "pool/owner"
  }),
  {
    header: (
      <TextWithDataTestId dataTestId="lbl_s3_abandoned_buckets_get_requests">
        <FormattedMessage id="getRequests" />
      </TextWithDataTestId>
    ),
    accessorKey: "get_object_count"
  },
  {
    header: (
      <TextWithDataTestId dataTestId="lbl_s3_abandoned_buckets_put_requests">
        <FormattedMessage id="putRequests" />
      </TextWithDataTestId>
    ),
    accessorKey: "put_object_count"
  },
  detectedAt({ headerDataTestId: "lbl_s3_abandoned_buckets_detected_at" }),
  possibleMonthlySavings({
    headerDataTestId: "lbl_s3_abandoned_buckets_savings",
    defaultSort: "desc"
  })
];

class AbandonedS3Buckets extends BaseRecommendation {
  type = "s3_abandoned_buckets";

  name = "abandonedS3Buckets";

  title = "abandonedS3Buckets";

  descriptionMessageId = "abandonedS3BucketsDescription";

  get descriptionMessageValues() {
    const {
      days_threshold: daysThreshold
    } = this.options;

    return { daysThreshold };
  }

  emptyMessageId = "noAbandonedS3Buckets";

  services = [AWS_S3];

  appliedDataSources = [AWS_CNR];

  categories = [CATEGORY.COST];

  hasSettings = true;

  settingsSidemodalClass = AbandonedS3BucketsModal;

  withExclusions = true;

  static resourceDescriptionMessageId = "abandonedS3BucketsResourceRecommendation";

  get previewItems() {
    return this.items.map((item) => [
      {
        key: `${item.cloud_resource_id}-${item.resource_id}-label`,
        value: <RecommendationListItemResourceLabel item={item} />
      },
      {
        key: `${item.cloud_resource_id}-${item.resource_id}-saving`,
        value: <FormattedMoney type={FORMATTED_MONEY_TYPES.COMMON} value={item.saving} />
      }
    ]);
  }

  columns = columns;
}

export default AbandonedS3Buckets;
