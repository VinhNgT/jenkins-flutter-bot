/**
 * MainScreen — Primary dashboard view.
 *
 * Composes BranchSelector, CustomBranchInput, ActiveBuilds, and RecentBuilds.
 * Manages branch selection state and the trigger build action.
 */

import { useCallback, useEffect, useMemo, useState } from 'preact/hooks';
import { usePlatform, usePrimaryButton, usePlatformStorage } from 'platform-core';
import { Scaffold, List, ListItem, Switch, Button } from 'tg-ui-preact';
import { useToast } from '../context/ToastContext';
import { triggerBuild } from '../api';
import BranchSelector from './BranchSelector';
import CustomBranchInput from './CustomBranchInput';
import ActiveBuilds from './ActiveBuilds';
import RecentBuilds from './RecentBuilds';
import type { AppConfig } from '../types';

interface MainScreenProps {
  config: AppConfig;
  isActive: boolean;
  onBuildSelect: (type: 'active' | 'recent', id: string) => void;
}

export default function MainScreen({ config, isActive, onBuildSelect }: MainScreenProps) {
  const { initData, haptic, hasNativePrimaryButton, showAlert } = usePlatform();
  const { showToast } = useToast();

  const [selectedBranch, setSelectedBranch] = useState<string | null>(null);
  const [customInput, setCustomInput] = useState('');
  const [isCustom, setIsCustom] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [recentRefreshKey, setRecentRefreshKey] = useState(0);
  const [notifyChat, setNotifyChat, notifyLoading] = usePlatformStorage('notify_completion', true);
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
  // Block trigger until PlatformStorage preference is loaded to avoid race conditions.
  const isDuplicate = config.active_builds.some((b) => b.ref === selectedBranch);
  const hasSelection = selectedBranch != null && selectedBranch.trim() !== '';
  const isVisible = (hasSelection && !isDuplicate && notifyLoaded) || isLoading;
  const isEnabled = isVisible && !isLoading;

  // Hide browser fallback trigger inside native primary-button host platforms
  const showFallbackButton = !hasNativePrimaryButton;

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
      showAlert(msg);
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
      showAlert(msg);
    } finally {
      setIsLoading(false);
    }
  }, [selectedBranch, isDuplicate, initData, haptic, showToast, notifyChat, showAlert]);

  // Declarative PrimaryButton — the hook manages show/hide, progress,
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

  usePrimaryButton(buttonConfig, isActive);

  return (
    <Scaffold title={config.app_name} subtitle="Select a target branch to deploy">

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
        <List footer="Send a chat message when the build finishes.">
          <ListItem
            id="notifyToggle"
            title="Notify on completion"
            rightElement={
              <Switch
                checked={notifyChat}
                onChange={(checked) => {
                  haptic.impact('light');
                  setNotifyChat(checked);
                }}
              />
            }
          />
        </List>
      )}

      <ActiveBuilds builds={config.active_builds} onSelect={(b) => onBuildSelect('active', b.request_id)} />

      <RecentBuilds refreshKey={recentRefreshKey} onSelect={(b) => onBuildSelect('recent', b.request_id)} />

      {/* App Version */}
      <div class="tg-section-footer build-fingerprint">
        v{config.app_version}
      </div>

      {/* Browser fallback trigger button (hidden in Telegram) */}
      {showFallbackButton && (
        <div id="fallbackBtnContainer" style={{ marginTop: 'auto', paddingTop: 'var(--space-lg)', width: '100%' }}>
          <Button
            id="fallbackTriggerBtn"
            disabled={!isEnabled}
            loading={isLoading}
            onClick={handleTrigger}
          >
            Trigger Build
          </Button>
        </div>
      )}
    </Scaffold>
  );
}
