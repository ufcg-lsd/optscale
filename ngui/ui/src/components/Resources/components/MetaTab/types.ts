import { ObjectValues } from "utils/types";
import { BREAKDOWN_FIELD_NAME, BREAKDOWN_TYPE } from "./constants";

type BreakdownDatum = { count: number; cost: number };

export type BreakdownTotals = Record<string, BreakdownDatum>;

export type Breakdown = Record<string, Record<string, BreakdownDatum>>;

type RequestParams = Record<string, string>;

export type TotalsTableProps = {
  startDate: number;
  endDate: number;
  totals: BreakdownTotals;
  metaName: string;
};

export type TableLoadingWrapperProps = {
  isLoading: boolean;
} & TotalsTableProps;

export type MetaProps = {
  dateRange: {
    startDate: number;
    endDate: number;
  };
  requestParams: RequestParams;
  metaNames: string[];
};

export type AvailableMetaFiltersProps = {
  requestParams: RequestParams;
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
  isLoading?: boolean;
};

export type HeadingProps = {
  breakdownBy: string;
  onBreakdownChange: (value: string) => void;
  metaNames: string[];
  breakdownType: BreakdownType;
  onBreakdownTypeChange: (value: BreakdownType) => void;
  applyFilterByCategory: boolean;
  onApplyFilterByCategoryChange: (value: boolean) => void;
  withLegend: boolean;
  onWithLegendChange: (value: boolean) => void;
};

export type ApplyFilterByCategoryToggleProps = {
  onChange: (value: boolean) => void;
  checked: boolean;
};
