import Slack from "components/Integrations/Slack";
import { useGetInstallationPathQuery } from "graphql/__generated__/hooks/slacker";
import { useCurrentEmployee } from "hooks/coreData/useCurrentEmployee";
import EmployeesService from "services/EmployeesService";

const IntegrationsSlackContainer = () => {
  const { useGet: useGetEmployees } = EmployeesService();
  const { isLoading: isGetEmployeesLoading, employees } = useGetEmployees();

  const { loading: isGetSlackInstallationPathLoading, data } = useGetInstallationPathQuery();

  const { slack_connected: isCurrentEmployeeConnectedToSlack = false } = useCurrentEmployee();

  return (
    <Slack
      totalEmployees={employees.length}
      connectedEmployees={employees.filter((el) => el.slack_connected).length}
      isCurrentEmployeeConnectedToSlack={isCurrentEmployeeConnectedToSlack}
      slackInstallationPath={data?.url}
      isLoadingProps={{ isGetEmployeesLoading, isGetSlackInstallationPathLoading }}
    />
  );
};

export default IntegrationsSlackContainer;
