/**
 * ActiveBuilds — Real-time active build list with cancel controls.
 *
 * Uses .tg-list-item, .spinner-ios, .pulsing-dot, .tg-cancel-action classes.
 * Cancel button is conditionally shown based on user ownership.
 */

import { useState } from 'preact/hooks';
import { Monitor, StopCircle } from 'lucide-preact';
import { useTelegram } from '../context/TelegramContext';
import { useToast } from '../context/ToastContext';
import { useRelativeTime } from '../hooks/useRelativeTime';
import { cancelBuild as cancelBuildApi } from '../api';
import type { ActiveBuild } from '../types';

interface ActiveBuildsProps {
  builds: ActiveBuild[];
}

/** Individual active build row with relative time and cancel. */
function ActiveBuildRow({ build }: { build: ActiveBuild }) {
  const { isTelegram, initData, userId, haptic, tg } = useTelegram();
  const { showToast } = useToast();
  const relativeTime = useRelativeTime(build.triggered_at);
  const [cancelling, setCancelling] = useState(false);

  // Allow cancellation if the current user triggered the build,
  // or in preview/emulator mode for testing.
  const canCancel = initData === 'preview' || (userId != null && build.triggered_by_id === userId);

  async function handleCancel() {
    haptic.impact('medium');

    if (isTelegram && tg) {
      tg.showPopup({
        title: 'Cancel Active Build',
        message: `Are you sure you want to stop the build running on branch '${build.ref}'? This action cannot be undone.`,
        buttons: [
          { id: 'cancel_build', type: 'destructive', text: 'Yes, Stop Build' },
          { id: 'dismiss', type: 'cancel', text: 'Keep Running' },
        ],
      }, async (buttonId) => {
        if (buttonId === 'cancel_build') {
          haptic.impact('heavy');
          await doCancelBuild();
        }
      });
    } else {
      if (confirm(`Are you sure you want to stop the build running on branch '${build.ref}'?`)) {
        await doCancelBuild();
      }
    }
  }

  async function doCancelBuild() {
    setCancelling(true);
    try {
      await cancelBuildApi(initData, build.request_id);
      haptic.notification('success');
      showToast('Build successfully cancelled.');
    } catch (err) {
      console.error(err);
      haptic.notification('error');
      showToast(err instanceof Error ? err.message : 'Failed to cancel build.', 'error');
      setCancelling(false);
    }
  }

  function handleRowClick() {
    const durInfo = relativeTime ? `Started: ${relativeTime}` : '';
    const text = `Target: ${build.label}\nRef: ${build.ref}\nTriggered by: ${build.triggered_by}\n${durInfo}`;
    if (isTelegram && tg) {
      tg.showAlert(text);
    } else {
      alert(`Active Build Details\n\n${text}`);
    }
  }

  return (
    <div class="tg-list-item" style={{ cursor: 'pointer' }} onClick={handleRowClick}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexGrow: 1 }}>
        {/* iOS-style spinner — custom SVG matching Telegram's native loading indicator */}
        <svg class="spinner-ios" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <circle cx="12" cy="12" r="10" stroke="var(--tg-color-divider)" stroke-width="2.5" />
          <path d="M12 2C6.47715 2 2 6.47715 2 12" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" />
        </svg>
        <div class="tg-list-item-content" style={{ minWidth: 0 }}>
          <span class="tg-list-item-title">{build.label}</span>
          <span class="tg-list-item-subtitle" style={{ display: 'flex', alignItems: 'center', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            <span class="pulsing-dot" style={{ flexShrink: 0 }} />
            <span>by {build.triggered_by} · {relativeTime}</span>
          </span>
          <div style={{ marginTop: '4px', display: 'flex' }}>
            <span class="tg-list-item-meta">{build.ref}</span>
          </div>
        </div>
      </div>
      <div class="tg-list-item-right" style={{ flexShrink: 0, paddingLeft: '8px' }} onClick={(e) => e.stopPropagation()}>
        {canCancel ? (
          <button
            class="tg-cancel-action"
            disabled={cancelling}
            onClick={handleCancel}
          >
            {cancelling ? (
              <svg class="spinner-ios" style={{ width: '12px', height: '12px', animationDuration: '0.6s' }} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="12" cy="12" r="10" stroke="rgba(255,59,48,0.15)" stroke-width="3" />
                <path d="M12 2C6.47715 2 2 6.47715 2 12" stroke="currentColor" stroke-width="3" stroke-linecap="round" />
              </svg>
            ) : (
              <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <StopCircle size={14} strokeWidth={2.5} /> Cancel
              </span>
            )}
          </button>
        ) : (
          <span style={{ fontSize: '13px', color: 'var(--tg-color-hint)', fontStyle: 'italic' }}>
            Locked
          </span>
        )}
      </div>
    </div>
  );
}

export default function ActiveBuilds({ builds }: ActiveBuildsProps) {
  return (
    <div class="tg-section">
      <div class="tg-section-header" style={{ display: 'flex', alignItems: 'center' }}>
        <span>Active Builds</span>
        {builds.length > 0 && (
          <span
            id="buildsCountBadge"
            style={{
              background: 'var(--tg-color-link)',
              color: 'var(--tg-color-button-text)',
              fontSize: '11px',
              padding: '2px 6px',
              borderRadius: '10px',
              fontWeight: 'bold',
              marginLeft: '6px',
            }}
          >
            {builds.length}
          </span>
        )}
      </div>
      <div class="tg-list" id="buildsList">
        {builds.length === 0 ? (
          <div class="tg-empty-row">
            <Monitor size={36} strokeWidth={2} style={{ opacity: 0.35, color: 'var(--tg-color-text)' }} />
            <span>No active build streams running.</span>
          </div>
        ) : (
          builds.map((build) => (
            <ActiveBuildRow key={build.request_id} build={build} />
          ))
        )}
      </div>
      <div class="tg-section-footer">
        Build progress updates in real-time. Only the user who triggered a build can cancel it.
      </div>
    </div>
  );
}
