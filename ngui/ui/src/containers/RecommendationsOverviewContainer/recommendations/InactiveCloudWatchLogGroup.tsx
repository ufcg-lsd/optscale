import { FormattedMessage } from "react-intl";
import FormattedMoney from "components/FormattedMoney";
import RecommendationListItemResourceLabel from "components/RecommendationListItemResourceLabel";
import TextWithDataTestId from "components/TextWithDataTestId";
import { AWS_EC2, AWS_S3 } from "hooks/useRecommendationServices";
import { detectedAt, possibleMonthlySavings, resource, resourceLocation } from "utils/columns";
import { AWS_CNR, FORMATTED_MONEY_TYPES } from "utils/constants";
import BaseRecommendation, { CATEGORY } from "./BaseRecommendation";

const columns = [
  resource({
    headerDataTestId: "lbl_iclw_resource"
  }),
  {
    header: (
      <TextWithDataTestId dataTestId="lbl_log_group_name">
        <FormattedMessage id="logGroupName" />
      </TextWithDataTestId>
    ),
    accessorKey: "log_group_name"
  },
  resourceLocation({
    headerDataTestId: "lbl_iclw_location"
  }),
  detectedAt({
    headerDataTestId: "lbl_iclw_detected_at"
  }),
  {
    header: (
      <TextWithDataTestId dataTestId="lbl_iclw_ingestion">
        <FormattedMessage id="ingestionLogGroup" />
      </TextWithDataTestId>
    ),
    accessorKey: "ingestion"
  },
  {
    header: (
      <TextWithDataTestId dataTestId="lbl_iclw_storage">
        <FormattedMessage id="storageLogGroup" />
      </TextWithDataTestId>
    ),
    accessorKey: "storage"
  },
  {
    header: (
      <TextWithDataTestId dataTestId="lbl_iclw_query">
        <FormattedMessage id="queryLogGroup" />
      </TextWithDataTestId>
    ),
    accessorKey: "query"
  },
  possibleMonthlySavings({
    headerDataTestId: "lbl_iclw_possible_monthly_savings",
    defaultSort: "desc"
  })
];

class InactiveCloudWatchLogGroup extends BaseRecommendation {
  type = "inactive_cloud_watch_log_group";

  name = "inactiveCloudWatchLogGroup";

  title = "inactiveCloudWatchLogGroupTitle";

  descriptionMessageId = "inactiveCloudWatchLogGroupDescription";

  emptyMessageId = "noInactiveCloudWatchLogGroup";

  services = [AWS_EC2, AWS_S3];

  appliedDataSources = [AWS_CNR];

  categories = [CATEGORY.COST];

  static resourceDescriptionMessageId = "inactiveCloudWatchLogGroupResourceRecommendation";

  columns = columns;

  get previewItems() {
    return this.items.map((item) => [
      {
        key: `${item.cloud_resource_id}-label`,
        value: <RecommendationListItemResourceLabel item={item} />
      },
      {
        key: `${item.cloud_resource_id}-saving`,
        value: <FormattedMoney type={FORMATTED_MONEY_TYPES.COMMON} value={item.saving} />
      }
    ]);
  }
}

export default InactiveCloudWatchLogGroup;
