import { Box, CircularProgress, FormControl } from "@mui/material";
import { useFormContext } from "react-hook-form";
import CodeBlock from "components/CodeBlock";
import { useCloudPoliciesLazyQuery } from "graphql/__generated__/hooks/restapi";
import { useOrganizationInfo } from "hooks/useOrganizationInfo";
import { AWS_CNR } from "utils/constants";
import { FIELD_NAMES as AWS_BILLING_BUCKET_FIELD_NAMES } from "../AwsBillingBucket";
import AwsShowRoleButton from "./AwsShowRoleButton";

const AwsAssumedRolePolicies = ({
  codeBlockHeight = "300px",
  fieldsRequiredForRoleFetch = []
}: {
  codeBlockHeight?: string;
  fieldsRequiredForRoleFetch: string[];
}) => {
  const { getValues } = useFormContext();
  const { organizationId } = useOrganizationInfo();
  const [getPolicies, { data: { cloudPolicies } = {}, loading: isLoading }] = useCloudPoliciesLazyQuery({
    fetchPolicy: "no-cache"
  });

  const onRoleButtonClick = () => {
    const bucketName = getValues(AWS_BILLING_BUCKET_FIELD_NAMES.BUCKET_NAME);

    getPolicies({
      variables: {
        organizationId: organizationId,
        params: {
          bucket_name: bucketName,
          cloud_type: AWS_CNR
        }
      }
    });
  };

  const text = JSON.stringify(cloudPolicies, null, 2);

  return (
    <>
      <AwsShowRoleButton onClick={onRoleButtonClick} fieldsRequiredForRoleFetch={fieldsRequiredForRoleFetch} />
      {(cloudPolicies || isLoading) && (
        <FormControl fullWidth>
          {isLoading ? (
            <Box
              sx={{
                display: "flex",
                justifyContent: "center",
                alignItems: "center",
                height: codeBlockHeight,
                backgroundColor: (theme) => theme.palette.background.default
              }}
            >
              <CircularProgress />
            </Box>
          ) : (
            <CodeBlock text={text} height={codeBlockHeight} />
          )}
        </FormControl>
      )}
    </>
  );
};

export default AwsAssumedRolePolicies;
