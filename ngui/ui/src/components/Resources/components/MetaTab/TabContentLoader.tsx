import { Box, Stack } from "@mui/material";
import Skeleton from "components/Skeleton";
import TableLoader from "components/TableLoader";
import { SPACING_1 } from "utils/layouts";
import BreakdownChart from "./BreakdownChart";
import { BREAKDOWN_TYPE, BREAKDOWN_FIELD_NAME } from "./constants";
import Heading from "./Heading";

const TabContentLoader = () => (
  <Stack spacing={SPACING_1}>
    <Box>
      <Skeleton fullWidth>
        <Heading
          breakdownBy=""
          onBreakdownChange={() => {}}
          metaNames={[]}
          breakdownType={BREAKDOWN_TYPE.EXPENSES}
          onBreakdownTypeChange={() => {}}
          onWithLegendChange={() => {}}
          applyFilterByCategory={false}
          onApplyFilterByCategoryChange={() => {}}
          withLegend
        />
      </Skeleton>
    </Box>
    <Box>
      <BreakdownChart
        isLoading
        breakdownBy=""
        breakdown={{}}
        totals={{}}
        field={BREAKDOWN_FIELD_NAME.COST}
        isPercentBreakdownType={false}
        withLegend
      />
    </Box>
    <Box>
      <TableLoader />
    </Box>
  </Stack>
);

export default TabContentLoader;
