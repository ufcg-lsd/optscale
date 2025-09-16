import { NetworkStatus } from "@apollo/client";
import { useOrganizationsQuery } from "graphql/__generated__/hooks/restapi";
import { useGetToken } from "hooks/useGetToken";
import { isEmpty as isEmptyArray } from "utils/arrays";
import { Error, Loading } from "../../common";
import ProceedToApplication from "../ProceedToApplication";
import SetupOrganization from "./SetupOrganization";

const StepContainer = () => {
  const { userEmail } = useGetToken();

  const {
    data: organizations,
    networkStatus: getOrganizationsNetworkStatus,
    error: getOrganizationsError,
    refetch: refetchOrganizations
  } = useOrganizationsQuery({
    fetchPolicy: "network-only",
    notifyOnNetworkStatusChange: true
  });

  const getOrganizationsLoading = getOrganizationsNetworkStatus === NetworkStatus.loading;

  if (getOrganizationsLoading) {
    return <Loading />;
  }

  if (getOrganizationsError) {
    return <Error />;
  }

  const hasOrganizations = !isEmptyArray(organizations?.organizations ?? []);

  if (!hasOrganizations) {
    return <SetupOrganization userEmail={userEmail} refetchOrganizations={refetchOrganizations} />;
  }

  return <ProceedToApplication />;
};

export default StepContainer;
