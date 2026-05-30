/**
 * BuildDetailScreen — Unified full-screen detail view for a build.
 *
 * Displays build metadata in Telegram-style grouped sections with
 * key-value rows. Renders a single continuous screen for all build
 * states: active (building), success, failure, timeout, and cancelled.
 *
 * Uses a shimmer skeleton on cold opens (tapping a recent build from
 * the list). When a build completes while the user is viewing it, the
 * screen transitions in-place — the last-known active build data stays
 * visible while the completed result loads, then the UI smoothly
 * updates (icon, subtitle, new rows) without any loading flash.
 */

import { useCallback, useEffect, useMemo, useState } from 'preact/hooks';
import {
  CheckCircle2, XCircle, Clock, AlertCircle,
  GitBranch, Hash, Timer, User, Calendar, CalendarCheck,
  Copy, Download, HardDrive, FileText,
} from 'lucide-preact';
import { usePlatform, usePrimaryButton } from 'platform-core';
import { Scaffold, List, Badge, Spinner, Button } from 'tg-ui-preact';
import { useToast } from '../context/ToastContext';
import { useRelativeTime } from '../hooks/useRelativeTime';
import { cancelBuild as cancelBuildApi, fetchRecentBuilds } from '../api';
import type { ActiveBuild, RecentBuild, AppConfig } from '../types';

interface BuildDetailScreenProps {
  config: AppConfig;
  type: 'active' | 'recent';
  id: string;
  /** Whether this screen is the active (topmost) screen.
   *  False during exit animation — triggers immediate MainButton/BackButton hide. */
  isActive: boolean;
  onBack: () => void;
}

/** Format a byte count as a human-readable file size. */
function formatFileSize(bytes: number): string {
  if (bytes === 0) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Format a duration in seconds as "Xm Ys". */
function formatDuration(seconds: number): string {
  if (seconds < 0) return '—';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  if (m === 0) return `${s}s`;
  return `${m}m ${s}s`;
}

/** Format a unix timestamp as a locale-aware date string. */
function formatTimestamp(ts: number): string {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** Map build result to icon component and color. */
function getResultVisuals(result: string) {
  switch (result) {
    case 'success':
      return { Icon: CheckCircle2, color: 'var(--tg-color-success)', bg: 'rgba(49, 181, 69, 0.1)', label: 'Success' };
    case 'failure':
      return { Icon: XCircle, color: 'var(--tg-color-destructive)', bg: 'rgba(255, 59, 48, 0.1)', label: 'Failed' };
    case 'timeout':
      return { Icon: Clock, color: 'var(--tg-color-warning)', bg: 'rgba(255, 149, 0, 0.1)', label: 'Timed Out' };
    case 'cancelled':
      return { Icon: AlertCircle, color: 'var(--tg-color-hint)', bg: 'rgba(142, 142, 147, 0.1)', label: 'Cancelled' };
    default:
      return { Icon: AlertCircle, color: 'var(--tg-color-hint)', bg: 'rgba(142, 142, 147, 0.1)', label: result };
  }
}

export default function BuildDetailScreen({ config, type, id, isActive, onBack }: BuildDetailScreenProps) {
  const platform = usePlatform();
  const { initData, userId, haptic, hasNativePrimaryButton } = platform;
  const { showToast } = useToast();
  const [cancelling, setCancelling] = useState(false);

  // Resolve build data: active builds come from live config, recent builds are fetched
  const [recentBuild, setRecentBuild] = useState<RecentBuild | null>(null);

  // Preserve the last-known active build so the screen stays populated
  // during the active→recent transition (build completes while viewing).
  const [lastActiveBuild, setLastActiveBuild] = useState<ActiveBuild | null>(null);

  const activeBuild = type === 'active'
    ? config.active_builds.find((b) => b.request_id === id) ?? null
    : null;

  // Snapshot the active build whenever it's available, so it persists
  // through the type switch from 'active' to 'recent'.
  useEffect(() => {
    if (activeBuild) {
      setLastActiveBuild(activeBuild);
    }
  }, [activeBuild]);

  useEffect(() => {
    if (type !== 'recent') return;
    fetchRecentBuilds(initData)
      .then((builds) => {
        const match = builds.find((b) => b.request_id === id);
        if (match) {
          setRecentBuild(match);
        } else {
          // Build not found — navigate back
          onBack();
        }
      })
      .catch(() => {
        onBack();
      });
  }, [type, id, initData, onBack]);

  // Determine the resolved data and current display mode.
  // During active→recent transition, fall back to the last active build
  // to keep the screen populated while the recent result loads.
  const isActiveBuild = type === 'active';
  const resolvedData: ActiveBuild | RecentBuild | null =
    isActiveBuild ? activeBuild : (recentBuild ?? lastActiveBuild);

  // Whether we're displaying active-style UI (spinner, cancel button).
  // True when actively building OR during the brief transition window
  // where we're showing cached active data while recent loads.
  const showingActiveUI = isActiveBuild || (!isActiveBuild && !recentBuild && lastActiveBuild !== null);

  // Shimmer skeleton loading state — only shown on cold opens
  // (e.g. tapping a recent build from the list), never during
  // live active→recent transitions.
  if (!resolvedData) {
    return (
      <Scaffold onBack={onBack}>
        {/* Skeleton: Hero header */}
        <div class="tg-detail-header">
          <div class="tg-skeleton" style={{ width: '56px', height: '56px', borderRadius: 'var(--radius-round)', marginBottom: 'var(--space-sm)' }} />
          <div class="tg-skeleton" style={{ width: '140px', height: '20px', borderRadius: 'var(--radius-md)' }} />
          <div class="tg-skeleton" style={{ width: '100px', height: '14px', borderRadius: 'var(--radius-sm)', marginTop: 'var(--space-xs)' }} />
        </div>
        {/* Skeleton: Build Information section */}
        <div class="tg-section">
          <div class="tg-section-header">
            <div class="tg-skeleton" style={{ width: '120px', height: '12px', borderRadius: 'var(--radius-sm)' }} />
          </div>
          <div class="tg-list">
            {[1, 2, 3, 4].map((i) => (
              <div class="tg-kv-row" key={i}>
                <div class="tg-skeleton" style={{ width: '80px', height: '14px', borderRadius: 'var(--radius-sm)' }} />
                <div class="tg-skeleton" style={{ width: '100px', height: '14px', borderRadius: 'var(--radius-sm)' }} />
              </div>
            ))}
          </div>
        </div>
        {/* Skeleton: Diagnostics section */}
        <div class="tg-section">
          <div class="tg-section-header">
            <div class="tg-skeleton" style={{ width: '90px', height: '12px', borderRadius: 'var(--radius-sm)' }} />
          </div>
          <div class="tg-list">
            <div class="tg-kv-row">
              <div class="tg-skeleton" style={{ width: '80px', height: '14px', borderRadius: 'var(--radius-sm)' }} />
              <div class="tg-skeleton" style={{ width: '140px', height: '14px', borderRadius: 'var(--radius-sm)' }} />
            </div>
          </div>
        </div>
      </Scaffold>
    );
  }

  // Derive common fields
  const label = showingActiveUI
    ? resolvedData.label ?? ''
    : (resolvedData as RecentBuild).label || (resolvedData as RecentBuild).branch;
  const ref = showingActiveUI
    ? (resolvedData as ActiveBuild).ref
    : (resolvedData as RecentBuild).branch;
  const triggeredAt = resolvedData.triggered_at;
  const requestId = resolvedData.request_id;

  // Active build fields
  const triggeredBy = showingActiveUI ? (resolvedData as ActiveBuild).triggered_by : null;
  const triggeredById = showingActiveUI ? (resolvedData as ActiveBuild).triggered_by_id : null;
  const canCancel = showingActiveUI && isActiveBuild && (initData === 'preview' || (userId != null && triggeredById === userId));
  const estimatedDurationMs = showingActiveUI ? (resolvedData as ActiveBuild).estimated_duration : 0;

  // Recent build fields
  const result = showingActiveUI ? null : (resolvedData as RecentBuild).result;
  const completedAt = showingActiveUI ? null : (resolvedData as RecentBuild).completed_at;
  const commitHash = showingActiveUI ? null : (resolvedData as RecentBuild).commit_hash;
  const downloadUrl = showingActiveUI ? null : (resolvedData as RecentBuild).download_url;
  const fileSize = showingActiveUI ? 0 : (resolvedData as RecentBuild).file_size;
  const buildNumber = showingActiveUI ? 0 : (resolvedData as RecentBuild).build_number;

  // Relative time for header subtitle
  const relativeTime = useRelativeTime(showingActiveUI ? triggeredAt : (completedAt ?? 0));

  // Visuals for header icon
  const visuals = showingActiveUI
    ? { Icon: Timer, color: 'var(--tg-color-warning)', bg: 'rgba(245, 158, 11, 0.1)', label: 'Building' }
    : getResultVisuals(result ?? '');

  // Duration (only for completed builds)
  const duration = completedAt && triggeredAt ? completedAt - triggeredAt : null;

  function handleBack() {
    onBack();
  }

  // --- Cancel build via tg.MainButton ---
  const handleCancel = useCallback(async () => {
    if (!canCancel) return;
    haptic.impact('medium');

    const doCancel = async () => {
      setCancelling(true);
      try {
        await cancelBuildApi(initData, requestId);
        haptic.notification('success');
        showToast('Build successfully cancelled.');
        onBack();
      } catch (err) {
        console.error(err);
        haptic.notification('error');
        const msg = err instanceof Error ? err.message : 'Failed to cancel build.';
        showToast(msg, 'error');
        setCancelling(false);
      }
    };

    const confirmed = await platform.showConfirm({
      title: 'Cancel Active Build',
      message: `Are you sure you want to stop the build running on branch '${ref}'? This action cannot be undone.`,
      confirmLabel: 'Yes, Stop Build',
      danger: true,
    });

    if (confirmed) {
      haptic.impact('heavy');
      await doCancel();
    }
  }, [canCancel, ref, requestId, initData, platform, haptic, showToast, onBack]);

  // Declarative MainButton — the hook manages show/hide, progress,
  // click handler registration, and cleanup automatically.
  const cancelButtonConfig = useMemo(() => {
    if (!canCancel) return null;
    return {
      text: 'CANCEL BUILD',
      color: 'var(--tg-color-destructive)',
      textColor: '#ffffff',
      loading: cancelling,
      disabled: cancelling,
      onClick: handleCancel,
    };
  }, [canCancel, cancelling, handleCancel]);

  usePrimaryButton(cancelButtonConfig, isActive);

  function handleCopyLink() {
    if (downloadUrl) {
      navigator.clipboard.writeText(downloadUrl);
      haptic.impact('soft');
      showToast('Copied to clipboard');
    }
  }

  const headerSubtitle = showingActiveUI
    ? `Building · started ${relativeTime}`
    : `${visuals.label} · ${relativeTime}`;

  const badgeVariant = result === 'success' ? 'success'
    : result === 'failure' ? 'danger'
    : result === 'timeout' ? 'warning'
    : 'neutral';

  return (
    <Scaffold onBack={handleBack}>
      {/* Hero header */}
      <div className="tg-detail-header">
        <div
          className="tg-detail-header-icon"
          style={{ backgroundColor: visuals.bg, color: visuals.color }}
        >
          {showingActiveUI ? (
            <Spinner size={28} />
          ) : (
            <visuals.Icon size={28} strokeWidth={2} />
          )}
        </div>
        <span className="tg-detail-header-title">{label}</span>
        <span className="tg-detail-header-subtitle">{headerSubtitle}</span>
      </div>

      {/* Build Information section */}
      <List header="Build Information">
        {result && (
          <div className="tg-kv-row">
            <span className="tg-kv-label">Status</span>
            <Badge variant={badgeVariant}>{result}</Badge>
          </div>
        )}
        <div className="tg-kv-row">
          <span className="tg-kv-label"><GitBranch size={15} style={{ verticalAlign: '-2px', marginRight: '4px' }} />Branch</span>
          <span className="tg-kv-value mono">{ref}</span>
        </div>
        {commitHash && (
          <div className="tg-kv-row">
            <span className="tg-kv-label"><Hash size={15} style={{ verticalAlign: '-2px', marginRight: '4px' }} />Commit</span>
            <span className="tg-kv-value mono">{commitHash.substring(0, 7)}</span>
          </div>
        )}
        {duration !== null && duration > 0 && (
          <div className="tg-kv-row">
            <span className="tg-kv-label"><Timer size={15} style={{ verticalAlign: '-2px', marginRight: '4px' }} />Duration</span>
            <span className="tg-kv-value">{formatDuration(duration)}</span>
          </div>
        )}
        {fileSize > 0 && (
          <div className="tg-kv-row">
            <span className="tg-kv-label"><HardDrive size={15} style={{ verticalAlign: '-2px', marginRight: '4px' }} />APK Size</span>
            <span className="tg-kv-value">{formatFileSize(fileSize)}</span>
          </div>
        )}
        {showingActiveUI && estimatedDurationMs > 0 && (
          <div className="tg-kv-row">
            <span className="tg-kv-label"><Timer size={15} style={{ verticalAlign: '-2px', marginRight: '4px' }} />Estimated</span>
            <span className="tg-kv-value">{formatDuration(estimatedDurationMs / 1000)}</span>
          </div>
        )}
        {triggeredBy && (
          <div className="tg-kv-row">
            <span className="tg-kv-label"><User size={15} style={{ verticalAlign: '-2px', marginRight: '4px' }} />Triggered by</span>
            <span className="tg-kv-value">{triggeredBy}</span>
          </div>
        )}
        <div className="tg-kv-row">
          <span className="tg-kv-label"><Calendar size={15} style={{ verticalAlign: '-2px', marginRight: '4px' }} />Started</span>
          <span className="tg-kv-value">{formatTimestamp(triggeredAt)}</span>
        </div>
        {completedAt && (
          <div className="tg-kv-row">
            <span className="tg-kv-label"><CalendarCheck size={15} style={{ verticalAlign: '-2px', marginRight: '4px' }} />Completed</span>
            <span className="tg-kv-value">{formatTimestamp(completedAt)}</span>
          </div>
        )}
      </List>

      {/* Actions section (success builds with download URL) */}
      {result === 'success' && downloadUrl && (
        <List header="Actions">
          <button className="tg-action-row" onClick={handleCopyLink} style={{ width: '100%', background: 'none', border: 'none', textAlign: 'left', font: 'inherit', color: 'inherit', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 'var(--space-md)' }}>
            <Copy size={20} />
            <span>Copy Download Link</span>
          </button>
          <a
            className="tg-action-row"
            href={downloadUrl}
            target="_blank"
            rel="noopener noreferrer"
            style={{ textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 'var(--space-md)' }}
          >
            <Download size={20} />
            <span>Download APK</span>
          </a>
        </List>
      )}

      {/* Diagnostics section */}
      <List header="Diagnostics">
        {buildNumber > 0 && (
          <div className="tg-kv-row">
            <span className="tg-kv-label"><Hash size={15} style={{ verticalAlign: '-2px', marginRight: '4px' }} />Jenkins Build</span>
            <span className="tg-kv-value mono">#{buildNumber}</span>
          </div>
        )}
        <div className="tg-kv-row">
          <span className="tg-kv-label"><FileText size={15} style={{ verticalAlign: '-2px', marginRight: '4px' }} />Request ID</span>
          <span className="tg-kv-value mono">{requestId}</span>
        </div>
      </List>

      {/* Browser fallback cancel button (hidden in Telegram — uses MainButton) */}
      {canCancel && !hasNativePrimaryButton && (
        <div style={{ marginTop: 'auto', paddingTop: 'var(--space-lg)', width: '100%' }}>
          <Button
            variant="danger"
            disabled={cancelling}
            loading={cancelling}
            onClick={handleCancel}
          >
            Cancel Build
          </Button>
        </div>
      )}
    </Scaffold>
  );
}
