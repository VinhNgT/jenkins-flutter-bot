/**
 * BranchSelector — Preconfigured branch radio list.
 *
 * Uses .tg-list-item, .tg-radio-icon, .selected classes from the
 * global TGUI stylesheet. Provides haptic feedback on selection.
 */

import { Check } from 'lucide-preact';
import { useTelegram } from '../context/TelegramContext';
import type { Branch } from '../types';

interface BranchSelectorProps {
  branches: Branch[];
  selectedBranch: string | null;
  onSelect(ref: string): void;
}

export default function BranchSelector({ branches, selectedBranch, onSelect }: BranchSelectorProps) {
  const { haptic } = useTelegram();

  function handleClick(ref: string) {
    haptic.tap();
    onSelect(ref);
  }

  return (
    <div class="tg-section">
      <div class="tg-section-header">Target Option</div>
      <div class="tg-list" id="branchesContainer">
        {branches.map((branch) => (
          <div
            key={branch.ref}
            class={`tg-list-item${selectedBranch === branch.ref ? ' selected' : ''}`}
            onClick={() => handleClick(branch.ref)}
          >
            <div class="tg-list-item-content" style={{ minWidth: 0 }}>
              <span class="tg-list-item-title">{branch.label}</span>
              <div style={{ marginTop: '2px', display: 'flex' }}>
                <span class="tg-list-item-meta">{branch.ref}</span>
              </div>
            </div>
            <div class="tg-radio-icon">
              <Check size={20} strokeWidth={2.5} />
            </div>
          </div>
        ))}
      </div>
      <div class="tg-section-footer">Choose one of the authorized branches for this environment.</div>
    </div>
  );
}
