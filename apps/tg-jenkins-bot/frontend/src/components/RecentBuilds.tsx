/**
 * RecentBuilds — Completed builds list with result badges and downloads.
 *
 * Uses .tg-result-badge, .tg-download-link classes from the TGUI stylesheet.
 */

import { useEffect, useState } from 'preact/hooks';
import { useTelegram } from '../context/TelegramContext';
import { useRelativeTime } from '../hooks/useRelativeTime';
import { fetchRecentBuilds } from '../api';
import type { RecentBuild } from '../types';

interface RecentBuildsProps {
  /** Incremented when a build completes to trigger a refetch. */
  refreshKey: number;
}

function RecentBuildRow({ build }: { build: RecentBuild }) {
  const relativeTime = useRelativeTime(build.completed_at);

  const commit = build.commit_hash ? build.commit_hash.substring(0, 7) : '';
  const branchInfo = commit ? `${build.branch} (${commit})` : build.branch;

  let durationStr = '';
  if (build.completed_at && build.triggered_at) {
    const dur = Math.max(0, Math.floor(build.completed_at - build.triggered_at));
    durationStr = dur < 60 ? ` · ${dur}s` : ` · ${Math.floor(dur / 60)}m`;
  }

  const emoji = build.result === 'success' ? '✅'
    : build.result === 'failure' ? '❌'
    : build.result === 'timeout' ? '⏰' : '🛑';

  return (
    <div class="tg-list-item" style={{ cursor: 'default' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexGrow: 1 }}>
        <div style={{ fontSize: '20px', display: 'flex', alignItems: 'center', justifyContent: 'center', width: '24px', height: '24px' }}>
          {emoji}
        </div>
        <div class="tg-list-item-content">
          <span class="tg-list-item-title">{branchInfo}</span>
          <span class="tg-list-item-subtitle">{relativeTime}{durationStr}</span>
        </div>
      </div>
      <div class="tg-list-item-right" style={{ flexShrink: 0, paddingLeft: '8px' }}>
        {build.result === 'success' && build.download_url ? (
          <a href={build.download_url} target="_blank" rel="noopener noreferrer" class="tg-download-link">
            📲 Download
          </a>
        ) : (
          <span class={`tg-result-badge ${build.result ?? 'cancelled'}`}>
            {build.result}
          </span>
        )}
      </div>
    </div>
  );
}

export default function RecentBuilds({ refreshKey }: RecentBuildsProps) {
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
          builds.map((build, i) => (
            <RecentBuildRow key={`${build.branch}-${build.completed_at}-${i}`} build={build} />
          ))
        )}
      </div>
      <div class="tg-section-footer">Shows the last completed builds with download links.</div>
    </div>
  );
}
