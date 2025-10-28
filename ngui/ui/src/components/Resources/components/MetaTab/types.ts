import { ObjectValues } from "utils/types";
import { BREAKDOWN_FIELD_NAME, BREAKDOWN_TYPE } from "./constants";

type BreakdownDatum = { count: number; cost: number };

export type BreakdownTotals = Record<string, BreakdownDatum>;

export type Breakdown = Record<string, Record<string, BreakdownDatum>>;

export type TotalsTableProps = {
  startDate: number;
  endDate: number;
  totals: BreakdownTotals;
  metaName: string;
};

export type TableLoadingWrapperProps = {
  isLoading: boolean;
} & TotalsTableProps;

export type ContentProps = {
  requestParams: Record<string, string>;
  metaNames: string[];
};

export type BreakdownType = ObjectValues<typeof BREAKDOWN_TYPE>;

export type BreakdownTypeSelectorProps = {
  value: BreakdownType;
  onChange: (value: BreakdownType) => void;
};

export type BreakdownChartProps = {
  breakdownBy: string;
  breakdown: Breakdown;
  totals: BreakdownTotals;
  field: ObjectValues<typeof BREAKDOWN_FIELD_NAME>;
  isPercentBreakdownType: boolean;
  withLegend: boolean;
  isLoading: boolean;
};

export type BreakdownBySelectorProps = {
  value: string;
  onChange: (value: string) => void;
  metaNames: string[];
};
