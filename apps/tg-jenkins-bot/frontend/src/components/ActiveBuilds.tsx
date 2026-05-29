/**
 * ActiveBuilds — Real-time active build list.
 *
 * Uses .tg-list-item, .spinner-ios, .pulsing-dot classes.
 * Tapping a row navigates to the build detail screen.
 */

import { Monitor } from 'lucide-preact';
import { useTelegram } from '../context/TelegramContext';
import { useRelativeTime } from '../hooks/useRelativeTime';
import type { ActiveBuild } from '../types';

interface ActiveBuildsProps {
  builds: ActiveBuild[];
  onSelect: (build: ActiveBuild) => void;
}

/** Format seconds into a human-readable duration string. */
function formatRemaining(seconds: number): string {
  if (seconds <= 0) return 'any moment';
  if (seconds < 60) return `~${seconds}s left`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return s > 0 ? `~${m}m ${s}s left` : `~${m}m left`;
}

/** Individual active build row with relative time and estimated remaining. */
function ActiveBuildRow({ build, onSelect }: { build: ActiveBuild; onSelect: (build: ActiveBuild) => void }) {
  const { haptic } = useTelegram();
  const relativeTime = useRelativeTime(build.triggered_at);

  // Compute estimated remaining from estimated_duration (ms) and elapsed time
  const elapsed = Math.floor(Date.now() / 1000 - build.triggered_at);
  const estimatedSec = build.estimated_duration > 0
    ? Math.floor(build.estimated_duration / 1000)
    : 0;
  const remaining = estimatedSec > 0 ? Math.max(0, estimatedSec - elapsed) : 0;

  function handleClick() {
    haptic.impact('light');
    onSelect(build);
  }

  return (
    <div class="tg-list-item" style={{ cursor: 'pointer' }} onClick={handleClick}>
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
            <span>
              by {build.triggered_by} · {relativeTime}
              {estimatedSec > 0 && ` · ${formatRemaining(remaining)}`}
            </span>
          </span>
        </div>
      </div>
    </div>
  );
}

export default function ActiveBuilds({ builds, onSelect }: ActiveBuildsProps) {
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
            <ActiveBuildRow key={build.request_id} build={build} onSelect={onSelect} />
          ))
        )}
      </div>
      <div class="tg-section-footer">
        Build progress updates in real-time. Tap a build for details and actions.
      </div>
    </div>
  );
}
