/**
 * RecentBuilds — Completed builds list with result badges.
 *
 * Uses .tg-result-badge classes from the TGUI stylesheet.
 * Tapping a row navigates to the build detail screen.
 */

import { useEffect, useState } from 'preact/hooks';
import { CheckCircle2, XCircle, Clock, AlertCircle } from 'lucide-preact';
import { useTelegram } from '../context/TelegramContext';
import { useRelativeTime } from '../hooks/useRelativeTime';
import { fetchRecentBuilds } from '../api';
import type { RecentBuild } from '../types';

interface RecentBuildsProps {
  /** Incremented when a build completes to trigger a refetch. */
  refreshKey: number;
  onSelect: (build: RecentBuild) => void;
}

function RecentBuildRow({ build, onSelect }: { build: RecentBuild; onSelect: (build: RecentBuild) => void }) {
  const { haptic } = useTelegram();
  const relativeTime = useRelativeTime(build.completed_at);

  const title = build.label || build.branch;
  const commit = build.commit_hash ? build.commit_hash.substring(0, 7) : '';

  const Icon = build.result === 'success' ? CheckCircle2
    : build.result === 'failure' ? XCircle
    : build.result === 'timeout' ? Clock : AlertCircle;

  const iconColor = build.result === 'success' ? 'var(--tg-color-button)'
    : build.result === 'failure' ? 'var(--tg-color-destructive)'
    : build.result === 'timeout' ? '#ff9500' : 'var(--tg-color-hint)';

  // Subtitle: relative time + short commit hash for identification
  const subtitle = commit ? `${relativeTime} · ${commit}` : relativeTime;

  function handleClick() {
    haptic.impact('light');
    onSelect(build);
  }

  return (
    <div class="tg-list-item" style={{ cursor: 'pointer' }} onClick={handleClick}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexGrow: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', color: iconColor, flexShrink: 0 }}>
          <Icon size={22} strokeWidth={2.5} />
        </div>
        <div class="tg-list-item-content" style={{ minWidth: 0 }}>
          <span class="tg-list-item-title">{title}</span>
          <span class="tg-list-item-subtitle" style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {subtitle}
          </span>
        </div>
      </div>
      <div class="tg-list-item-right" style={{ flexShrink: 0, paddingLeft: '8px' }}>
        <span class={`tg-result-badge ${build.result ?? 'cancelled'}`}>
          {build.result}
        </span>
      </div>
    </div>
  );
}

export default function RecentBuilds({ refreshKey, onSelect }: RecentBuildsProps) {
  const { initData } = useTelegram();
  const [builds, setBuilds] = useState<RecentBuild[]>([]);

  useEffect(() => {
    fetchRecentBuilds(initData)
      .then(setBuilds)
      .catch((err) => console.error('Failed to fetch recent builds:', err));
  }, [initData, refreshKey]);

  return (
    <div class="tg-section">
      <div class="tg-section-header">Recent Builds</div>
      <div class="tg-list" id="recentBuildsList">
        {builds.length === 0 ? (
          <div class="tg-empty-row" style={{ padding: '16px', textAlign: 'center', color: 'var(--tg-color-hint)' }}>
            <span>No recent builds yet.</span>
          </div>
        ) : (
          builds.map((build) => (
            <RecentBuildRow key={build.request_id} build={build} onSelect={onSelect} />
          ))
        )}
      </div>
      <div class="tg-section-footer">Tap a build for details, download links, and diagnostics.</div>
    </div>
  );
}
