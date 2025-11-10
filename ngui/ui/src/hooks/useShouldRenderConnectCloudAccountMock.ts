import { isEmptyArray } from "utils/arrays";
import { useAllDataSources } from "./coreData/useAllDataSources";

export const useShouldRenderConnectCloudAccountMock = (dataSourceType) => {
  const dataSources = useAllDataSources();

  return dataSourceType
    ? dataSources.findIndex((dataSource) => dataSource.type === dataSourceType) === -1
    : isEmptyArray(dataSources);
};
