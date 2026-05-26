/**
 * CustomBranchInput — Free-text branch input with clear button.
 *
 * Uses .tg-input-row, .tg-input-field, .tg-input-clear classes.
 * Fires onCustomBranch() when the user types, clearing any preset selection.
 */

import { useRef } from 'preact/hooks';
import { useTelegram } from '../context/TelegramContext';

interface CustomBranchInputProps {
  value: string;
  isSelected: boolean;
  onInput(value: string): void;
  onClear(): void;
}

export default function CustomBranchInput({ value, isSelected, onInput, onClear }: CustomBranchInputProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const { haptic } = useTelegram();

  function handleInput(e: Event) {
    const val = (e.target as HTMLInputElement).value;
    onInput(val);
    if (val.trim()) haptic.tap();
  }

  function handleClear() {
    haptic.impact('light');
    onClear();
    inputRef.current?.focus();
  }

  function handleFocus() {
    haptic.tap();
  }

  const populated = value.trim() !== '';
  const rowClasses = [
    'tg-list-item',
    isSelected ? 'selected' : '',
    populated ? 'populated' : '',
  ].filter(Boolean).join(' ');

  return (
    <div class="tg-section">
      <div class="tg-section-header">Custom Branch</div>
      <div class="tg-list">
        <div class={rowClasses} id="customBranchRow">
          <div class="tg-input-row">
            <input
              ref={inputRef}
              type="text"
              class="tg-input-field"
              id="customBranchInput"
              placeholder="Or enter custom branch name..."
              value={value}
              onInput={handleInput}
              onFocus={handleFocus}
            />
            <div class="tg-input-clear" id="customInputClear" onClick={handleClear}>
              ✕
            </div>
          </div>
        </div>
      </div>
      <div class="tg-section-footer">Type in a custom ref if the target branch is not in the whitelist.</div>
    </div>
  );
}
