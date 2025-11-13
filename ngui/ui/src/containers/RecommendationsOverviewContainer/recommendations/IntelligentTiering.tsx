/**
 * IntelligentTiering.tsx
 * 
 * This file defines the IntelligentTiering recommendation class that extends BaseRecommendation.
 * It provides the structure and configuration for displaying intelligent tiering recommendations
 * in the OptScale frontend.
 * 
 * The file contains:
 * - Column definitions for the recommendations table display
 * - Class properties for recommendation type, name, title, and metadata
 * - Preview items configuration for card view display
 * 
 */

import { FormattedMessage } from "react-intl";

import FormattedMoney from "components/FormattedMoney";
import RecommendationListItemResourceLabel from "components/RecommendationListItemResourceLabel";
import TextWithDataTestId from "components/TextWithDataTestId";
import { AWS_S3 } from "hooks/useRecommendationServices";
import { detectedAt, possibleMonthlySavings, resource, resourceLocation } from "utils/columns";
import { AWS_CNR, FORMATTED_MONEY_TYPES } from "utils/constants";
import BaseRecommendation, { CATEGORY } from "./BaseRecommendation";

const columns = [
  resource({
    headerDataTestId: "intelligent_tiering"
  }),
  resourceLocation({
    headerDataTestId: "intelligent_tiering_location",
    typeAccessor: "cloud_type"
  }),
  {
    header: (
      <TextWithDataTestId dataTestId="intelligent_tiering_is_with_intelligent_tiering">
        <FormattedMessage id="intelligentTiering" />
      </TextWithDataTestId>
    ),
    accessorKey: "is_with_intelligent_tiering",
    cell: ({ cell }: { cell: { getValue: () => boolean } }) => {
      const value = cell.getValue();

      return <FormattedMessage id={value ? "yes" : "no"} />;
    }
  },
  detectedAt({ headerDataTestId: "intelligent_tiering_detected_at" }),
  possibleMonthlySavings({
    headerDataTestId: "intelligent_tiering_savings",
    defaultSort: "desc"
  })
];

class IntelligentTiering extends BaseRecommendation {
  type = "s3_intelligent_tiering";

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
    return this.items.map((item) => [
      { key: `${item.cloud_resource_id}-label`, value: <RecommendationListItemResourceLabel item={item} /> },
      {
        key: `${item.cloud_resource_id}-${item.resource_id}-saving`,
        value: <FormattedMoney type={FORMATTED_MONEY_TYPES.COMMON} value={item.saving} />
      }
    ]);
  }

  columns = columns as never[];
}

export default IntelligentTiering;
