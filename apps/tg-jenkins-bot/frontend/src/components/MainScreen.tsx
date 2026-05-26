/**
 * MainScreen — Primary dashboard view.
 *
 * Composes BranchSelector, CustomBranchInput, ActiveBuilds, and RecentBuilds.
 * Manages branch selection state and the trigger build action.
 */

import { useCallback, useEffect, useState } from 'preact/hooks';
import { useTelegram } from '../context/TelegramContext';
import { useToast } from '../context/ToastContext';
import { triggerBuild } from '../api';
import BranchSelector from './BranchSelector';
import CustomBranchInput from './CustomBranchInput';
import ActiveBuilds from './ActiveBuilds';
import RecentBuilds from './RecentBuilds';
import type { AppConfig } from '../types';

interface MainScreenProps {
  config: AppConfig;
}

export default function MainScreen({ config }: MainScreenProps) {
  const { tg, isTelegram, initData, haptic } = useTelegram();
  const { showToast } = useToast();

  const [selectedBranch, setSelectedBranch] = useState<string | null>(null);
  const [customInput, setCustomInput] = useState('');
  const [isCustom, setIsCustom] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [recentRefreshKey, setRecentRefreshKey] = useState(0);

  // Detect when a build disappears from active → trigger recent builds refresh
  const [prevBuildIds, setPrevBuildIds] = useState<string[]>([]);
  useEffect(() => {
    const currentIds = config.active_builds.map((b) => b.request_id);
    const hasCompleted = prevBuildIds.some((id) => !currentIds.includes(id));
    if (hasCompleted) {
      setRecentRefreshKey((k) => k + 1);
    }
    setPrevBuildIds(currentIds);
  }, [config.active_builds]);

  // Check if selected branch already has an active build
  const isDuplicate = config.active_builds.some((b) => b.ref === selectedBranch);
  const isEnabled = selectedBranch != null && selectedBranch.trim() !== '' && !isDuplicate && !isLoading;

  // Sync MainButton visibility
  useEffect(() => {
    if (!isTelegram || !tg) return;

    if (isEnabled) {
      tg.MainButton.setParams({
        text: 'TRIGGER BUILD',
        color: tg.themeParams.button_color ?? '#2481cc',
        text_color: tg.themeParams.button_text_color ?? '#ffffff',
        is_active: true,
        is_visible: true,
      });
    } else {
      tg.MainButton.hide();
    }
  }, [isEnabled, isTelegram, tg]);


  // Hide browser fallback trigger inside Telegram
  const showFallbackButton = !isTelegram;

  function handlePresetSelect(ref: string) {
    setCustomInput('');
    setIsCustom(false);
    setSelectedBranch(ref);
  }

  function handleCustomInput(value: string) {
    const trimmed = value.trim();
    setCustomInput(value);
    if (trimmed) {
      setIsCustom(true);
      setSelectedBranch(trimmed);
    } else {
      setIsCustom(false);
      setSelectedBranch(null);
    }
  }

  function handleCustomClear() {
    setCustomInput('');
    setIsCustom(false);
    setSelectedBranch(null);
  }

  const handleTrigger = useCallback(async () => {
    if (!selectedBranch) return;

    // Show duplicate toast before hitting the API
    if (isDuplicate) {
      showToast(`A build on '${selectedBranch}' is already running. Please wait or cancel it first.`, 'error');
      return;
    }

    haptic.impact('medium');
    setIsLoading(true);

    if (isTelegram && tg) {
      tg.MainButton.showProgress(false);
      tg.MainButton.disable();
    }

    try {
      await triggerBuild(initData, selectedBranch);

      // Reset selection
      setSelectedBranch(null);
      setCustomInput('');
      setIsCustom(false);

      haptic.notification('success');
      showToast('Build successfully triggered!');
    } catch (err) {
      console.error(err);
      haptic.notification('error');
      showToast(err instanceof Error ? err.message : 'Failed to trigger build. Please retry.', 'error');
    } finally {
      setIsLoading(false);
      if (isTelegram && tg) {
        tg.MainButton.hideProgress();
        tg.MainButton.enable();
      }
    }
  }, [selectedBranch, isDuplicate, initData, isTelegram, tg, haptic, showToast]);

  // Register MainButton click handler
  useEffect(() => {
    if (!isTelegram || !tg) return;
    tg.MainButton.onClick(handleTrigger);
    // Hide BackButton on main screen
    tg.BackButton.hide();

    return () => {
      tg.MainButton.offClick(handleTrigger);
    };
  }, [isTelegram, tg, handleTrigger]);

  return (
    <div class="container" id="mainScreen" style={{ display: 'flex' }}>
      <header>
        <div>
          <h1 id="appName">{config.app_name}</h1>
          <p class="header-subtitle">Select a target branch to deploy</p>
        </div>
      </header>

      <BranchSelector
        branches={config.branches}
        selectedBranch={isCustom ? null : selectedBranch}
        onSelect={handlePresetSelect}
      />

      <CustomBranchInput
        value={customInput}
        isSelected={isCustom}
        onInput={handleCustomInput}
        onClear={handleCustomClear}
      />

      <ActiveBuilds builds={config.active_builds} />

      <RecentBuilds refreshKey={recentRefreshKey} />

      {/* Diagnostic fingerprint */}
      <div class="tg-section-footer build-fingerprint">
        Preact {/* version marker for cache diagnostics */}
      </div>

      {/* Browser fallback trigger button (hidden in Telegram) */}
      {showFallbackButton && (
        <div id="fallbackBtnContainer" style={{ marginTop: 'auto', paddingTop: '16px', width: '100%' }}>
          <button
            id="fallbackTriggerBtn"
            class="tg-primary-button"
            disabled={!isEnabled}
            onClick={handleTrigger}
          >
            {isLoading ? (
              <svg class="spinner-ios" style={{ color: 'var(--tg-color-button-text)' }} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="12" cy="12" r="10" stroke="rgba(255,255,255,0.15)" stroke-width="3" />
                <path d="M12 2C6.47715 2 2 6.47715 2 12" stroke="currentColor" stroke-width="3" stroke-linecap="round" />
              </svg>
            ) : (
              <span>Trigger Build</span>
            )}
          </button>
        </div>
      )}
    </div>
  );
}
