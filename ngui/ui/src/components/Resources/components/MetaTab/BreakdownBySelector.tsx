import Selector, { Item, ItemContent } from "components/Selector";
import { getMetaFormattedName } from "utils/metadata";
import { BreakdownBySelectorProps } from "./types";

const BreakdownBySelector = ({ value, onChange, metaNames }: BreakdownBySelectorProps) => (
  <Selector id="resources-meta-categorize-by-selector" labelMessageId="categorizeBy" value={value} onChange={onChange}>
    {metaNames
      .map((name) => ({
        value: name,
        name: getMetaFormattedName(name)
      }))
      .sort((a, b) => a.name.localeCompare(b.name))
      .map((breakdown) => (
        <Item key={breakdown.value} value={breakdown.value}>
          <ItemContent>{breakdown.name}</ItemContent>
        </Item>
      ))}
  </Selector>
);

export default BreakdownBySelector;
