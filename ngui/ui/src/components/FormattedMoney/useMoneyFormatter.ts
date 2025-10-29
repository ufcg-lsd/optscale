import { useCallback } from "react";
import { IntlShape, useIntl } from "react-intl";
import { formatCompactNumber } from "components/CompactFormattedNumber";
import { useOrganizationInfo } from "hooks/useOrganizationInfo";
import { FORMATTED_MONEY_TYPES } from "utils/constants";

const ONE_DOLLAR = 1;
const COMPACT_VALUE_THRESHOLD = 1000;

type FormatParams = {
  value: number;
  format?: string;
  absoluteValue: number;
  maximumFractionDigits?: number;
};

type Formatter = IntlShape["formatNumber"];

const formatLessThanOne =
  (formatter: Formatter) =>
  ({ format }: { format?: string }) =>
    `< ${formatter(1, { format })}`;

const formatCompactMoney =
  (formatter: Formatter) =>
  ({ value, format }: { value: number; format?: string }) =>
    formatCompactNumber(formatter)({ value, format: format ? `${format}Compact` : undefined });

const formatCommon =
  (formatter: Formatter) =>
  ({ value, format, absoluteValue }: FormatParams) =>
    absoluteValue < ONE_DOLLAR ? formatLessThanOne(formatter)({ format }) : formatter(value, { format });

const formatCompact =
  (formatter: Formatter) =>
  ({ value, format, absoluteValue }: FormatParams) => {
    if (absoluteValue >= COMPACT_VALUE_THRESHOLD) {
      return formatCompactMoney(formatter)({ value, format });
    }
    return absoluteValue < ONE_CENT ? formatApproximatelyZero(formatter)({ format }) : formatter(value, { format });
  };

const formatTiny =
  (formatter: Formatter) =>
  ({ value, format, maximumFractionDigits = 4 }: FormatParams) =>
    formatter(value, { format, maximumFractionDigits });

const formatTinyCompact =
  (formatter: Formatter) =>
  ({ value, format, maximumFractionDigits = 4 }: FormatParams) => {
    if (Math.abs(value) >= COMPACT_VALUE_THRESHOLD) {
      return formatCompactMoney(formatter)({ value, format });
    }

    return formatter(value, { format, maximumFractionDigits });
  };

export const useMoneyFormatter = () => {
  const { currency } = useOrganizationInfo();
  const intl = useIntl();

  return useCallback(
    (type: string, value: number, { format, ...rest }: { format?: string; [key: string]: unknown } = {}) => {
      const calculatedFormat = format || currency;

      if (!value && value !== 0) {
        return intl.formatNumber(0, { format: calculatedFormat });
      }

      const formatter = {
        [FORMATTED_MONEY_TYPES.COMMON]: formatCommon,
        [FORMATTED_MONEY_TYPES.COMPACT]: formatCompact,
        [FORMATTED_MONEY_TYPES.TINY_COMPACT]: formatTinyCompact,
        [FORMATTED_MONEY_TYPES.TINY]: formatTiny
      }[type];

      if (!formatter) {
        return intl.formatNumber(value, { format: calculatedFormat });
      }

      return formatter(intl.formatNumber)({
        value,
        absoluteValue: Math.abs(value),
        format: calculatedFormat,
        ...rest
      });
    },
    [currency, intl]
  );
};
