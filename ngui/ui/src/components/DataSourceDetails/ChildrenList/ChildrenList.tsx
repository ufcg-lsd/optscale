import Typography from "@mui/material/Typography";
import { FormattedMessage } from "react-intl";
import CloudLabel from "components/CloudLabel";
import SubTitle from "components/SubTitle";
import { useAllDataSources } from "hooks/coreData/useAllDataSources";
import { isEmptyArray } from "utils/arrays";

const ChildrenList = ({ parentId }) => {
  const dataSources = useAllDataSources();

  const childDataSources = dataSources.filter(({ parent_id: accountParentId }) => accountParentId === parentId);

  return (
    <>
      <SubTitle>
        <FormattedMessage id="childDataSources" />
      </SubTitle>
      {isEmptyArray(childDataSources) ? (
        <Typography>
          <FormattedMessage id="noChildDataSourcesDiscovered" />
        </Typography>
      ) : (
        childDataSources.map(({ id, name, type }) => <CloudLabel key={id} id={id} name={name} type={type} />)
      )}
    </>
  );
};

export default ChildrenList;
