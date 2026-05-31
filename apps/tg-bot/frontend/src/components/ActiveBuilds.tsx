import { Monitor } from 'lucide-preact';
import { usePlatform } from 'platform-core';
import { List, ListItem, Spinner } from 'tg-ui-preact';
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
  const { haptic } = usePlatform();
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
    <ListItem
      title={build.label}
      subtitle={
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <span className="pulsing-dot" style={{ flexShrink: 0 }} />
          <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            by {build.triggered_by} · {relativeTime}
            {estimatedSec > 0 && ` · ${formatRemaining(remaining)}`}
          </span>
        </div>
      }
      prefix={<Spinner size={22} />}
      onClick={handleClick}
    />
  );
}

export default function ActiveBuilds({ builds, onSelect }: ActiveBuildsProps) {
  const activeCountBadge = builds.length > 0 ? (
    <span
      id="buildsCountBadge"
      style={{
        background: 'var(--tg-color-link)',
        color: 'var(--tg-color-button-text)',
        fontSize: 'var(--font-size-xs)',
        padding: 'var(--space-xxs) var(--space-xs)',
        borderRadius: 'var(--radius-round)',
        fontWeight: 'bold',
        marginLeft: 'var(--space-xs)',
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center'
      }}
    >
      {builds.length}
    </span>
  ) : null;

  return (
    <List
      header={
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <span>Active Builds</span>
          {activeCountBadge}
        </div>
      }
      footer="Build progress updates in real-time. Tap a build for details and actions."
      id="buildsList"
    >
      {builds.length === 0 ? (
        <div className="tg-empty-row">
          <Monitor size={36} strokeWidth={2} style={{ opacity: 0.35, color: 'var(--tg-color-text)' }} />
          <span>No active build streams running.</span>
        </div>
      ) : (
        builds.map((build) => (
          <ActiveBuildRow key={build.request_id} build={build} onSelect={onSelect} />
        ))
      )}
    </List>
  );
}
