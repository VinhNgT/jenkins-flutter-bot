/**
 * RecentBuilds — Completed builds list with result badges and downloads.
 *
 * Uses .tg-result-badge, .tg-download-link classes from the TGUI stylesheet.
 */

import { useEffect, useState } from 'preact/hooks';
import { CheckCircle2, XCircle, Clock, AlertCircle, Copy, Download } from 'lucide-preact';
import { useTelegram } from '../context/TelegramContext';
import { useToast } from '../context/ToastContext';
import { useRelativeTime } from '../hooks/useRelativeTime';
import { fetchRecentBuilds } from '../api';
import type { RecentBuild } from '../types';

interface RecentBuildsProps {
  /** Incremented when a build completes to trigger a refetch. */
  refreshKey: number;
}

function RecentBuildRow({ build }: { build: RecentBuild }) {
  const { haptic, isTelegram, tg } = useTelegram();
  const { showToast } = useToast();
  const relativeTime = useRelativeTime(build.completed_at);

  const title = build.label || build.branch;
  const commit = build.commit_hash ? build.commit_hash.substring(0, 7) : '';

  const Icon = build.result === 'success' ? CheckCircle2
    : build.result === 'failure' ? XCircle
    : build.result === 'timeout' ? Clock : AlertCircle;

  const iconColor = build.result === 'success' ? 'var(--tg-color-button)'
    : build.result === 'failure' ? 'var(--tg-color-destructive)'
    : build.result === 'timeout' ? '#ff9500' : 'var(--tg-color-hint)';

  function handleCopy() {
    if (build.download_url) {
      navigator.clipboard.writeText(build.download_url);
      haptic.impact('soft');
      showToast('Download link copied to clipboard!');
    }
  }

  function handleRowClick() {
    // If the user wants to see the full branch name and commit, they can tap the row.
    const fullBranchInfo = commit ? `${build.branch} (${commit})` : build.branch;
    const text = `Target: ${title}\nRef: ${fullBranchInfo}`;
    if (isTelegram && tg) {
      tg.showAlert(text);
    } else {
      alert(`Build Details\n\n${text}`);
    }
  }

  return (
    <div class="tg-list-item" style={{ cursor: 'pointer' }} onClick={handleRowClick}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexGrow: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', color: iconColor, flexShrink: 0 }}>
          <Icon size={22} strokeWidth={2.5} />
        </div>
        <div class="tg-list-item-content" style={{ minWidth: 0 }}>
          <span class="tg-list-item-title">{title}</span>
          <span class="tg-list-item-subtitle" style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {relativeTime}
          </span>
          <div style={{ marginTop: '4px', display: 'flex' }}>
            <span class="tg-list-item-meta">
              {commit ? `${build.branch} (${commit})` : build.branch}
            </span>
          </div>
        </div>
      </div>
      <div class="tg-list-item-right" style={{ flexShrink: 0, paddingLeft: '8px', display: 'flex', gap: '12px', alignItems: 'center' }} onClick={(e) => e.stopPropagation()}>
        {build.result === 'success' && build.download_url ? (
          <>
            <button onClick={handleCopy} style={{ color: 'var(--tg-color-button)', background: 'none', border: 'none', padding: '0', display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer', fontSize: '14px', fontWeight: '500' }}>
              <Copy size={16} /> Copy
            </button>
            <a href={build.download_url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--tg-color-button)', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '14px', fontWeight: '500' }}>
              <Download size={16} /> Get
            </a>
          </>
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
