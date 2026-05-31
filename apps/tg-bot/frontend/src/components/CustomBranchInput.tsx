import { usePlatform } from 'platform-core';
import { List, Input } from 'tg-ui-preact';

interface CustomBranchInputProps {
  value: string;
  isSelected: boolean;
  onInput(value: string): void;
  onClear(): void;
}

/**
 * CustomBranchInput — Free-text branch input with clear button.
 *
 * Wraps the shared Input primitive in a List container, mapping
 * value change and clear events seamlessly with haptic feedback.
 */
export default function CustomBranchInput({ value, isSelected, onInput, onClear }: CustomBranchInputProps) {
  const { haptic } = usePlatform();

  function handleChange(val: string) {
    if (val === '') {
      haptic.impact('light');
      onClear();
    } else {
      onInput(val);
      if (val.trim()) haptic.impact('light');
    }
  }

  return (
    <List
      header="Custom Branch"
      footer="Type in a custom ref if the target branch is not in the whitelist."
    >
      <div
        className={`tg-list-item ${isSelected ? 'selected' : ''}`}
        style={{ padding: '0 var(--space-xl)' }}
        id="customBranchRow"
      >
        <Input
          value={value}
          onChange={handleChange}
          placeholder="Or enter custom branch name..."
          clearable
        />
      </div>
    </List>
  );
}
