import { useState } from "react";
import { useInvitationsQuery } from "graphql/__generated__/hooks/restapi";
import { isEmpty as isEmptyArray } from "utils/arrays";
import { Error, Loading } from "../../common";
import SetupOrganization from "../SetupOrganization/StepContainer";
import AcceptInvitations from "./AcceptInvitations";

const StepContainer = () => {
  const [proceedToNext, setProceedToNext] = useState(false);

  const {
    data: invitations,
    loading: getInvitationsLoading,
    error: getInvitationsError,
    refetch: refetchInvitations
  } = useInvitationsQuery({
    fetchPolicy: "network-only"
  });

  const isLoading = getInvitationsLoading;

  const error = getInvitationsError;

  if (isLoading) {
    return <Loading />;
  }

  if (error) {
    return <Error />;
  }

  if (proceedToNext) {
    return <SetupOrganization />;
  }

  const hasInvitations = !isEmptyArray(invitations?.invitations ?? []);

  if (hasInvitations) {
    return (
      <AcceptInvitations
        invitations={invitations?.invitations ?? []}
        refetchInvitations={refetchInvitations}
        onProceed={() => {
          setProceedToNext(true);
        }}
      />
    );
  }

  return <SetupOrganization />;
};

export default StepContainer;
