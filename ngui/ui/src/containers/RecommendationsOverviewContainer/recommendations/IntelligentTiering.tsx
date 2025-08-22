import { FormattedMessage } from "react-intl";
import RecommendationListItemResourceLabel from "components/RecommendationListItemResourceLabel";
import TextWithDataTestId from "components/TextWithDataTestId";
import { AWS_S3 } from "hooks/useRecommendationServices";
import { detectedAt, poolOwner, resource, resourceLocation } from "utils/columns";
import { AWS_CNR } from "utils/constants";
import BaseRecommendation, { CATEGORY } from "./BaseRecommendation";

const columns = [
  resource({
    headerDataTestId: "intelligent_tiering"
  }),
  resourceLocation({
    headerDataTestId: "intelligent_tiering_location",
    typeAccessor: "cloud_type"
  }),
  poolOwner({
    headerDataTestId: "intelligent_tiering_pool_owner",
    id: "pool/owner"
  }),
  {
    header: (
      <TextWithDataTestId dataTestId="intelligent_tiering_is_with_intelligent_tiering">
        <FormattedMessage id="intelligentTiering" />
      </TextWithDataTestId>
    ),
    accessorKey: "is_with_intelligent_tiering",
    cell: ({ cell }: { cell: { getValue: () => any } }) => {
      const value = cell.getValue();

      return <FormattedMessage id={value ? "yes" : "no"} />;
    }
  },
  detectedAt({ headerDataTestId: "intelligent_tiering_detected_at" })
];

class IntelligentTiering extends BaseRecommendation {
  type = "intelligent_tiering";

  name = "intelligentTiering";

  title = "intelligentTieringTitle";

  descriptionMessageId = "intelligentTieringDescription";

  emptyMessageId = "noIntelligentTiering";

  services = [AWS_S3];  

  appliedDataSources = [AWS_CNR];

  categories = [CATEGORY.COST];

  withExclusions = true;

  static resourceDescriptionMessageId = "intelligentTieringResourceRecommendation";

  get previewItems() {
    return this.items.map((item: any) => [
      { key: `${item.cloud_resource_id}-label`, value: <RecommendationListItemResourceLabel key={item.id} item={item} /> }
    ]);
  }

  columns = columns as never[];
}

export default IntelligentTiering;
