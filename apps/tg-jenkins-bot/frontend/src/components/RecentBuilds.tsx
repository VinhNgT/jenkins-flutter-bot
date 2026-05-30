import { useEffect, useState } from 'preact/hooks';
import { CheckCircle2, XCircle, Clock, AlertCircle } from 'lucide-preact';
import { usePlatform } from 'platform-core';
import { List, ListItem, Badge } from 'tg-ui-preact';
import { useRelativeTime } from '../hooks/useRelativeTime';
import { fetchRecentBuilds } from '../api';
import type { RecentBuild } from '../types';

interface RecentBuildsProps {
  /** Incremented when a build completes to trigger a refetch. */
  refreshKey: number;
  onSelect: (build: RecentBuild) => void;
}

function RecentBuildRow({ build, onSelect }: { build: RecentBuild; onSelect: (build: RecentBuild) => void }) {
  const { haptic } = usePlatform();
  const relativeTime = useRelativeTime(build.completed_at);

  const title = build.label || build.branch;
  const commit = build.commit_hash ? build.commit_hash.substring(0, 7) : '';

  const Icon = build.result === 'success' ? CheckCircle2
    : build.result === 'failure' ? XCircle
    : build.result === 'timeout' ? Clock : AlertCircle;

  const iconColor = build.result === 'success' ? 'var(--tg-color-success)'
    : build.result === 'failure' ? 'var(--tg-color-destructive)'
    : build.result === 'timeout' ? 'var(--tg-color-warning)' : 'var(--tg-color-hint)';

  // Subtitle: build number + relative time + short commit hash for identification
  const parts: string[] = [];
  if (build.build_number > 0) parts.push(`#${build.build_number}`);
  parts.push(relativeTime);
  if (commit) parts.push(commit);
  const subtitle = parts.join(' · ');

  function handleClick() {
    haptic.impact('light');
    onSelect(build);
  }

  const badgeVariant = build.result === 'success' ? 'success'
    : build.result === 'failure' ? 'danger'
    : build.result === 'timeout' ? 'warning'
    : 'neutral';

  return (
    <ListItem
      title={title}
      subtitle={subtitle}
      prefix={
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', color: iconColor }}>
          <Icon size={22} strokeWidth={2.5} />
        </div>
      }
      rightElement={
        <Badge variant={badgeVariant}>
          {build.result ?? 'cancelled'}
        </Badge>
      }
      onClick={handleClick}
    />
  );
}

export default function RecentBuilds({ refreshKey, onSelect }: RecentBuildsProps) {
  const { initData } = usePlatform();
  const [builds, setBuilds] = useState<RecentBuild[]>([]);

  useEffect(() => {
    fetchRecentBuilds(initData)
      .then(setBuilds)
      .catch((err) => console.error('Failed to fetch recent builds:', err));
  }, [initData, refreshKey]);

  return (
    <List
      header="Recent Builds"
      footer="Tap a build for details, download links, and diagnostics."
      id="recentBuildsList"
    >
      {builds.length === 0 ? (
        <div className="tg-empty-row" style={{ padding: 'var(--space-lg)', textAlign: 'center', color: 'var(--tg-color-hint)' }}>
          <span>No recent builds yet.</span>
        </div>
      ) : (
        builds.map((build) => (
          <RecentBuildRow key={build.request_id} build={build} onSelect={onSelect} />
        ))
      )}
    </List>
  );
}
