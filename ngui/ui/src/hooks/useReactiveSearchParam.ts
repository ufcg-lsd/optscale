import { useCallback, useEffect, useState } from "react";
import { areSearchParamsEqual } from "api/utils";
import { addSearchParamsChangeListener, removeSearchParamsChangeListener } from "utils/events";
import { getSearchParams } from "utils/network";

export const useReactiveSearchParam = (paramName: string) => {
  const [paramValue, setParamValue] = useState(() => {
    const allParams = getSearchParams();
    return allParams[paramName];
  });

  const listener = useCallback(
    (event) => {
      const { params } = event.detail;
      const newValue = params[paramName];

      if (!areSearchParamsEqual({ [paramName]: newValue }, { [paramName]: paramValue })) {
        setParamValue(newValue);
      }
    },
    [paramName, paramValue]
  );

  useEffect(() => {
    addSearchParamsChangeListener(listener);
    return () => removeSearchParamsChangeListener(listener);
  }, [listener]);

  return paramValue;
};
