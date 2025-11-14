import { ReactNode } from "react";
import { CLEAN_EXPENSES_BREAKDOWN_TYPES, CLEAN_EXPENSES_GROUP_TYPES } from "utils/constants";
import { ObjectValues, TODO } from "utils/types";

export type ExpensesBreakdownData = {
  breakdownBy: string;
  groupBy?: {
    groupType?: ObjectValues<typeof CLEAN_EXPENSES_GROUP_TYPES> | undefined;
    groupBy?: string;
  };
};

export type ResourceCountBreakdownData = {
  breakdownBy: string;
};

export type MetaBreakdownData = {
  breakdownBy: string;
};

export type BreakdownData = ExpensesBreakdownData | ResourceCountBreakdownData | MetaBreakdownData;

export type RenderDataItem = {
  controlName: string;
  renderValue: () => ReactNode;
};

export type ResourcesPerspectiveValuesDescriptionProps = {
  breakdownBy: ObjectValues<typeof CLEAN_EXPENSES_BREAKDOWN_TYPES>;
  breakdownData: BreakdownData;
  perspectiveFilterValues?: Record<string, TODO>;
  perspectiveAppliedFilters?: Record<string, TODO>;
};
