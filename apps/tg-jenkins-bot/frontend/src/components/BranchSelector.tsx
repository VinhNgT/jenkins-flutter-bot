import { usePlatform } from 'platform-core';
import { List, ListItem } from 'tg-ui-preact';
import type { Branch } from '../types';

interface BranchSelectorProps {
  branches: Branch[];
  selectedBranch: string | null;
  onSelect(ref: string): void;
}

/**
 * BranchSelector — Preconfigured branch radio list.
 *
 * Consolidates the selection list to use shared List and ListItem components,
 * while automatically mapping the selected state and trigger feedback.
 */
export default function BranchSelector({ branches, selectedBranch, onSelect }: BranchSelectorProps) {
  const { haptic } = usePlatform();

  function handleClick(ref: string) {
    haptic.impact('light');
    onSelect(ref);
  }

  return (
    <List
      header="Target Option"
      footer="Choose one of the authorized branches for this environment."
      className="branches-selector-list"
    >
      {branches.map((branch) => (
        <ListItem
          key={branch.ref}
          title={branch.label}
          meta={branch.ref}
          selected={selectedBranch === branch.ref}
          onClick={() => handleClick(branch.ref)}
        />
      ))}
    </List>
  );
}
