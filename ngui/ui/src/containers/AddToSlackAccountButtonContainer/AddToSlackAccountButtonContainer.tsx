import ButtonLoader from "components/ButtonLoader";
import { useGetInstallationPathQuery } from "graphql/__generated__/hooks/slacker";
import SlackIcon from "icons/SlackIcon";

const AddToSlackAccountButtonContainer = () => {
  const { loading, data } = useGetInstallationPathQuery();

  return (
    <ButtonLoader
      isLoading={loading}
      startIcon={<SlackIcon />}
      color="primary"
      variant="outlined"
      href={data?.url}
      messageId="addToSlack"
    />
  );
};

export default AddToSlackAccountButtonContainer;
