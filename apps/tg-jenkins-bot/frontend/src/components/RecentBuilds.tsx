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
  const { haptic } = useTelegram();
  const { showToast } = useToast();
  const relativeTime = useRelativeTime(build.completed_at);

  const commit = build.commit_hash ? build.commit_hash.substring(0, 7) : '';
  const branchInfo = commit ? `${build.branch} (${commit})` : build.branch;

  let durationStr = '';
  if (build.completed_at && build.triggered_at) {
    const dur = Math.max(0, Math.floor(build.completed_at - build.triggered_at));
    durationStr = dur < 60 ? ` · ${dur}s` : ` · ${Math.floor(dur / 60)}m`;
  }

  const Icon = build.result === 'success' ? CheckCircle2
    : build.result === 'failure' ? XCircle
    : build.result === 'timeout' ? Clock : AlertCircle;

  const iconColor = build.result === 'success' ? 'var(--tg-color-button)' // Green or Primary? Telegram usually uses primary or success color, we'll use button color or native success. Let's stick to standard colors. Let's use a nice hex or inherit. Actually, let's use standard colors: success=#34c759, failure=#ff3b30, timeout=#ff9500
    : build.result === 'failure' ? 'var(--tg-color-destructive)'
    : build.result === 'timeout' ? '#ff9500' : 'var(--tg-color-hint)';

  function handleCopy() {
    if (build.download_url) {
      navigator.clipboard.writeText(build.download_url);
      haptic.impact('soft');
      showToast('Download link copied to clipboard!');
    }
  }

  return (
    <div class="tg-list-item" style={{ cursor: 'default' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexGrow: 1 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', color: iconColor }}>
          <Icon size={22} strokeWidth={2.5} />
        </div>
        <div class="tg-list-item-content">
          <span class="tg-list-item-title">{branchInfo}</span>
          <span class="tg-list-item-subtitle">{relativeTime}{durationStr}</span>
        </div>
      </div>
      <div class="tg-list-item-right" style={{ flexShrink: 0, paddingLeft: '8px', display: 'flex', gap: '12px', alignItems: 'center' }}>
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
