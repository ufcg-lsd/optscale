import { isEmptyObject } from "utils/objects";

const getBarColor = (colorsMap) => (bar) => colorsMap[bar.id];

export const useBarChartColors = (palette, colorsMap) => (isEmptyObject(colorsMap) ? [...palette] : getBarColor(colorsMap));
