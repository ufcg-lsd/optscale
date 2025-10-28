import { Box, Stack } from "@mui/material";
import ChartLegendToggle from "components/ChartLegendToggle";
import { useMetaBreakdownQuery } from "graphql/__generated__/hooks/restapi";
import { useOrganizationInfo } from "hooks/useOrganizationInfo";
import { useSyncQueryParamWithState } from "hooks/useSyncQueryParamWithState";
import { mapAvailableFilterKeys } from "services/AvailableFiltersService";
import {
  DAILY_META_BREAKDOWN_BY_PARAMETER_NAME,
  DAILY_META_BREAKDOWN_TYPE_PARAMETER_NAME,
  WITH_LEGEND_QUERY_PARAMETER_NAME
} from "urls";
import { SPACING_1 } from "utils/layouts";
import BreakdownBySelector from "./BreakdownBySelector";
import BreakdownChart from "./BreakdownChart";
import BreakdownTypeSelector from "./BreakdownTypeSelector";
import { BREAKDOWN_TYPE, BREAKDOWN_FIELD_NAME } from "./constants";
import TotalsTable from "./TotalsTable";
import { ContentProps } from "./types";

const Content = ({ requestParams, metaNames }: ContentProps) => {
  const { organizationId } = useOrganizationInfo();

  const [breakdownBy, setBreakdownBy] = useSyncQueryParamWithState({
    queryParamName: DAILY_META_BREAKDOWN_BY_PARAMETER_NAME,
    defaultValue: metaNames[0] ?? "",
    possibleStates: metaNames
  });

  const [breakdownType, setBreakdownType] = useSyncQueryParamWithState({
    queryParamName: DAILY_META_BREAKDOWN_TYPE_PARAMETER_NAME,
    defaultValue: BREAKDOWN_TYPE.EXPENSES,
    possibleStates: Object.values(BREAKDOWN_TYPE)
  });

  const [withLegend, setWithLegend] = useSyncQueryParamWithState({
    queryParamName: WITH_LEGEND_QUERY_PARAMETER_NAME,
    possibleStates: [true, false],
    defaultValue: true
  });

  const { data: metaBreakdownData, loading: isLoadingMetaBreakdown } = useMetaBreakdownQuery({
    variables: {
      organizationId,
      params: {
        ...mapAvailableFilterKeys(requestParams),
        start_date: Number(requestParams.startDate),
        end_date: Number(requestParams.endDate),
        breakdown_by: breakdownBy
      }
    }
  });

  const field =
    breakdownType === BREAKDOWN_TYPE.EXPENSES || breakdownType === BREAKDOWN_TYPE.EXPENSES_PERCENT
      ? BREAKDOWN_FIELD_NAME.COST
      : BREAKDOWN_FIELD_NAME.COUNT;

  const isPercentBreakdownType =
    breakdownType === BREAKDOWN_TYPE.EXPENSES_PERCENT || breakdownType === BREAKDOWN_TYPE.COUNT_PERCENT;

  return (
    <Stack spacing={SPACING_1}>
      <Box display="flex" gap={SPACING_1}>
        <BreakdownBySelector value={breakdownBy} onChange={setBreakdownBy} metaNames={metaNames} />
        <BreakdownTypeSelector value={breakdownType} onChange={setBreakdownType} />
        <ChartLegendToggle checked={withLegend} onChange={setWithLegend} />
      </Box>
      <Box>
        <BreakdownChart
          breakdownBy={breakdownBy}
          breakdown={metaBreakdownData?.metaBreakdown?.breakdown ?? {}}
          totals={metaBreakdownData?.metaBreakdown?.totals ?? {}}
          field={field}
          withLegend={withLegend}
          isLoading={isLoadingMetaBreakdown}
          isPercentBreakdownType={isPercentBreakdownType}
        />
      </Box>
      <Box>
        <TotalsTable
          metaName={breakdownBy}
          startDate={Number(requestParams.startDate)}
          endDate={Number(requestParams.endDate)}
          totals={metaBreakdownData?.metaBreakdown?.totals ?? {}}
          isLoading={isLoadingMetaBreakdown}
        />
      </Box>
    </Stack>
  );
};

export default Content;
