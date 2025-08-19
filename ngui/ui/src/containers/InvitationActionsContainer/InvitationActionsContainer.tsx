import CheckOutlinedIcon from "@mui/icons-material/CheckOutlined";
import CloseOutlinedIcon from "@mui/icons-material/CloseOutlined";
import ButtonLoader from "components/ButtonLoader";
import { useUpdateInvitationMutation } from "graphql/__generated__/hooks/restapi";

const InvitationActionsContainer = ({ invitationId, onSuccessAccept, onSuccessDecline, buttonSize = "small" }) => {
  const [updateInvitation, { loading: loginLoading }] = useUpdateInvitationMutation();

  const onAccept = () => {
    updateInvitation({ variables: { invitationId, action: "accept" } }).then(() => {
      if (typeof onSuccessAccept === "function") {
        onSuccessAccept();
      }
    });
  };

  const onDecline = () => {
    updateInvitation({ variables: { invitationId, action: "decline" } }).then(() => {
      if (typeof onSuccessAccept === "function") {
        onSuccessDecline();
      }
    });
  };

  const isButtonLoading = loginLoading;

  return (
    <>
      <ButtonLoader
        size={buttonSize}
        messageId="accept"
        color="success"
        variant="contained"
        onClick={onAccept}
        isLoading={isButtonLoading}
        startIcon={<CheckOutlinedIcon />}
      />
      <ButtonLoader
        size={buttonSize}
        messageId="decline"
        color="error"
        onClick={onDecline}
        isLoading={isButtonLoading}
        startIcon={<CloseOutlinedIcon />}
      />
    </>
  );
};

export default InvitationActionsContainer;
