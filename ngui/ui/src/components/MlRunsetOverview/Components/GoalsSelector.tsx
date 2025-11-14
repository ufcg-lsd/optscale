import SettingsIcon from "@mui/icons-material/Settings";
import { ListItemText, MenuItem } from "@mui/material";
import { FormattedMessage } from "react-intl";
import Checkbox from "components/Checkbox";
import IconButton from "components/IconButton";
import Popover from "components/Popover";
import Tooltip from "components/Tooltip";
import { isEmptyArray } from "utils/arrays";
import { sliceByLimitWithEllipsis } from "utils/strings";

const Title = ({ messageId }) => (
  <MenuItem style={{ pointerEvents: "none" }}>
    <ListItemText primary={<FormattedMessage id={messageId} />} />
  </MenuItem>
);

const MAX_LIST_ITEM_TEXT_LENGTH = 40;

const GoalsSelector = ({ hyperparametersDimensionsNames, goalDimensionsNames, getGoalDimensionName, selected, onChange }) => {
  const isItemSelected = (item) => selected.includes(item);

  const removeItemFromSelected = (item) => selected.filter((selectedItem) => selectedItem !== item);

  const handleChange = (item) => {
    const newSelected = isItemSelected(item) ? removeItemFromSelected(item) : [...selected, item];

    onChange(newSelected);
  };

  const renderItems = (items, getText) =>
    items.map((item) => {
      const text = getText(item);

      const isTextLong = text.length > MAX_LIST_ITEM_TEXT_LENGTH;

      return (
        <MenuItem key={item} value={item} onClick={() => handleChange(item)}>
          <Checkbox size="small" checked={isItemSelected(item)} />
          <ListItemText
            primary={
              <Tooltip title={isTextLong ? text : undefined}>
                {isTextLong ? sliceByLimitWithEllipsis(text, MAX_LIST_ITEM_TEXT_LENGTH) : text}
              </Tooltip>
            }
          />
        </MenuItem>
      );
    });

  return (
    <Popover
      label={<IconButton icon={<SettingsIcon fontSize="small" />} />}
      menu={
        <>
          {isEmptyArray(hyperparametersDimensionsNames) ? null : (
            <>
              <Title messageId="hyperparameters" />
              {renderItems(hyperparametersDimensionsNames, (item) => item)}
            </>
          )}
          {isEmptyArray(goalDimensionsNames) ? null : (
            <>
              <Title messageId="goals" />
              {renderItems(goalDimensionsNames, (item) => getGoalDimensionName(item))}
            </>
          )}
        </>
      }
    />
  );
};

export default GoalsSelector;
