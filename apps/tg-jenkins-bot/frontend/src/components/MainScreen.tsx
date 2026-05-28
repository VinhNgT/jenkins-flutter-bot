/**
 * MainScreen — Primary dashboard view.
 *
 * Composes BranchSelector, CustomBranchInput, ActiveBuilds, and RecentBuilds.
 * Manages branch selection state and the trigger build action.
 */

import { useCallback, useEffect, useMemo, useState } from 'preact/hooks';
import { useTelegram } from '../context/TelegramContext';
import { useToast } from '../context/ToastContext';
import { triggerBuild } from '../api';
import BranchSelector from './BranchSelector';
import CustomBranchInput from './CustomBranchInput';
import ActiveBuilds from './ActiveBuilds';
import RecentBuilds from './RecentBuilds';
import { useMainButton } from '../hooks/useMainButton';
import { useCloudStorage } from '../hooks/useCloudStorage';
import type { AppConfig } from '../types';

interface MainScreenProps {
  config: AppConfig;
  isActive: boolean;
  onBuildSelect: (type: 'active' | 'recent', id: string) => void;
}

export default function MainScreen({ config, isActive, onBuildSelect }: MainScreenProps) {
  const { tg, isTelegram, initData, haptic } = useTelegram();
  const { showToast } = useToast();

  const [selectedBranch, setSelectedBranch] = useState<string | null>(null);
  const [customInput, setCustomInput] = useState('');
  const [isCustom, setIsCustom] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [recentRefreshKey, setRecentRefreshKey] = useState(0);
  const [notifyChat, setNotifyChat, notifyLoading] = useCloudStorage('notify_completion', true);
  const notifyLoaded = !notifyLoading;

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

  // Check if selected branch already has an active build.
  // Block trigger until CloudStorage preference is loaded to avoid race conditions.
  const isDuplicate = config.active_builds.some((b) => b.ref === selectedBranch);
  const hasSelection = selectedBranch != null && selectedBranch.trim() !== '';
  const isVisible = (hasSelection && !isDuplicate && notifyLoaded) || isLoading;
  const isEnabled = isVisible && !isLoading;


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

    // Show duplicate alert before hitting the API
    if (isDuplicate) {
      const msg = `A build on '${selectedBranch}' is already running. Please wait or cancel it first.`;
      if (isTelegram && tg) tg.showAlert(msg);
      else showToast(msg, 'error');
      return;
    }

    haptic.impact('medium');
    setIsLoading(true);

    try {
      await triggerBuild(initData, selectedBranch, notifyChat);

      // Reset selection
      setSelectedBranch(null);
      setCustomInput('');
      setIsCustom(false);

      haptic.notification('success');
      showToast('Build successfully triggered!');
    } catch (err) {
      console.error(err);
      haptic.notification('error');
      const msg = err instanceof Error ? err.message : 'Failed to trigger build. Please retry.';
      if (isTelegram && tg) tg.showAlert(msg);
      else showToast(msg, 'error');
    } finally {
      setIsLoading(false);
    }
  }, [selectedBranch, isDuplicate, initData, isTelegram, tg, haptic, showToast, notifyChat]);

  // Declarative MainButton — the hook manages show/hide, progress,
  // click handler registration, and cleanup automatically.
  const buttonConfig = useMemo(() => {
    if (!isVisible) return null;
    return {
      text: 'TRIGGER BUILD',
      loading: isLoading,
      disabled: !isEnabled,
      onClick: handleTrigger,
    };
  }, [isVisible, isLoading, isEnabled, handleTrigger]);

  useMainButton(buttonConfig, isActive);

  // Hide BackButton on main screen
  useEffect(() => {
    if (!isTelegram || !tg || !isActive) return;
    tg.BackButton.hide();
  }, [isTelegram, tg, isActive]);

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

      {notifyLoaded && (
        <div class="tg-section">
          <div class="tg-list">
            <div
              class="tg-list-item"
              id="notifyToggle"
              onClick={() => { haptic.tap(); setNotifyChat(!notifyChat); }}
            >
              <div class="tg-list-item-content">
                <span class="tg-list-item-title">Notify on completion</span>
              </div>
              <div class={`tg-toggle-track${notifyChat ? ' tg-toggle-on' : ''}`}>
                <div class="tg-toggle-thumb" />
              </div>
            </div>
          </div>
          <div class="tg-section-footer">Send a chat message when the build finishes.</div>
        </div>
      )}

      <ActiveBuilds builds={config.active_builds} onSelect={(b) => onBuildSelect('active', b.request_id)} />

      <RecentBuilds refreshKey={recentRefreshKey} onSelect={(b) => onBuildSelect('recent', b.request_id)} />

      {/* App Version */}
      <div class="tg-section-footer build-fingerprint">
        v{config.app_version}
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
