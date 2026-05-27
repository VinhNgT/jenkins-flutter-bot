/**
 * BuildDetailScreen — Full-screen detail view for a build.
 *
 * Displays build metadata in Telegram-style grouped sections with
 * key-value rows. Supports both active builds (with cancel action)
 * and completed recent builds (with download actions).
 */

import { useCallback, useEffect, useState } from 'preact/hooks';
import {
  CheckCircle2, XCircle, Clock, AlertCircle,
  GitBranch, Hash, Timer, User, Calendar, CalendarCheck,
  Copy, Download, HardDrive, FileText,
} from 'lucide-preact';
import { useTelegram } from '../context/TelegramContext';
import { useToast } from '../context/ToastContext';
import { useRelativeTime } from '../hooks/useRelativeTime';
import { cancelBuild as cancelBuildApi } from '../api';
import type { ActiveBuild, RecentBuild } from '../types';

type BuildDetailBuild =
  | { type: 'active'; data: ActiveBuild }
  | { type: 'recent'; data: RecentBuild };

interface BuildDetailScreenProps {
  build: BuildDetailBuild;
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
      return { Icon: CheckCircle2, color: '#31b545', bg: 'rgba(49, 181, 69, 0.1)', label: 'Success' };
    case 'failure':
      return { Icon: XCircle, color: 'var(--tg-color-destructive)', bg: 'rgba(255, 59, 48, 0.1)', label: 'Failed' };
    case 'timeout':
      return { Icon: Clock, color: '#ff9500', bg: 'rgba(255, 149, 0, 0.1)', label: 'Timed Out' };
    case 'cancelled':
      return { Icon: AlertCircle, color: 'var(--tg-color-hint)', bg: 'rgba(142, 142, 147, 0.1)', label: 'Cancelled' };
    default:
      return { Icon: AlertCircle, color: 'var(--tg-color-hint)', bg: 'rgba(142, 142, 147, 0.1)', label: result };
  }
}

export default function BuildDetailScreen({ build, onBack }: BuildDetailScreenProps) {
  const { isTelegram, tg, initData, userId, haptic } = useTelegram();
  const { showToast } = useToast();
  const [cancelling, setCancelling] = useState(false);

  const isActive = build.type === 'active';
  const data = build.data;

  // Derive common fields
  const label = isActive ? data.label : (data as RecentBuild).label || (data as RecentBuild).branch;
  const ref = isActive ? (data as ActiveBuild).ref : (data as RecentBuild).branch;
  const triggeredAt = data.triggered_at;
  const requestId = isActive ? (data as ActiveBuild).request_id : (data as RecentBuild).request_id;

  // Active build fields
  const triggeredBy = isActive ? (data as ActiveBuild).triggered_by : null;
  const triggeredById = isActive ? (data as ActiveBuild).triggered_by_id : null;
  const canCancel = isActive && (initData === 'preview' || (userId != null && triggeredById === userId));

  // Recent build fields
  const result = isActive ? null : (data as RecentBuild).result;
  const completedAt = isActive ? null : (data as RecentBuild).completed_at;
  const commitHash = isActive ? null : (data as RecentBuild).commit_hash;
  const downloadUrl = isActive ? null : (data as RecentBuild).download_url;
  const fileSize = isActive ? 0 : (data as RecentBuild).file_size;

  // Relative time for header subtitle
  const relativeTime = useRelativeTime(isActive ? triggeredAt : (completedAt ?? 0));

  // Visuals for header icon
  const visuals = isActive
    ? { Icon: Timer, color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.1)', label: 'Building' }
    : getResultVisuals(result ?? '');

  // Duration (only for completed builds)
  const duration = completedAt && triggeredAt ? completedAt - triggeredAt : null;

  // --- Cancel build via tg.MainButton ---
  const handleCancel = useCallback(async () => {
    if (!canCancel) return;
    haptic.impact('medium');

    const doCancel = async () => {
      setCancelling(true);
      if (isTelegram && tg) {
        tg.MainButton.showProgress(false);
        tg.MainButton.disable();
      }
      try {
        await cancelBuildApi(initData, requestId);
        haptic.notification('success');
        showToast('Build successfully cancelled.');
        onBack();
      } catch (err) {
        console.error(err);
        haptic.notification('error');
        const msg = err instanceof Error ? err.message : 'Failed to cancel build.';
        if (isTelegram && tg) tg.showAlert(msg);
        else showToast(msg, 'error');
        setCancelling(false);
        if (isTelegram && tg) {
          tg.MainButton.hideProgress();
          tg.MainButton.enable();
        }
      }
    };

    if (isTelegram && tg) {
      tg.showPopup({
        title: 'Cancel Active Build',
        message: `Are you sure you want to stop the build running on branch '${ref}'? This action cannot be undone.`,
        buttons: [
          { id: 'cancel_build', type: 'destructive', text: 'Yes, Stop Build' },
          { id: 'dismiss', type: 'cancel', text: 'Keep Running' },
        ],
      }, async (buttonId) => {
        if (buttonId === 'cancel_build') {
          haptic.impact('heavy');
          await doCancel();
        }
      });
    } else {
      if (confirm(`Are you sure you want to stop the build running on branch '${ref}'?`)) {
        await doCancel();
      }
    }
  }, [canCancel, ref, requestId, initData, isTelegram, tg, haptic, showToast, onBack]);

  // Wire tg.BackButton and tg.MainButton
  useEffect(() => {
    if (!isTelegram || !tg) return;

    tg.BackButton.show();
    tg.BackButton.onClick(onBack);

    if (canCancel) {
      tg.MainButton.setParams({
        text: 'CANCEL BUILD',
        color: '#ff3b30',
        text_color: '#ffffff',
        is_active: !cancelling,
        is_visible: true,
      });
      tg.MainButton.onClick(handleCancel);
    } else {
      tg.MainButton.hide();
    }

    return () => {
      tg.BackButton.offClick(onBack);
      tg.BackButton.hide();
      tg.MainButton.hide();
      if (canCancel) {
        tg.MainButton.offClick(handleCancel);
      }
    };
  }, [isTelegram, tg, onBack, canCancel, cancelling, handleCancel]);

  function handleCopyLink() {
    if (downloadUrl) {
      navigator.clipboard.writeText(downloadUrl);
      haptic.impact('soft');
      showToast('Download link copied to clipboard!');
    }
  }

  const headerSubtitle = isActive
    ? `Building · started ${relativeTime}`
    : `${visuals.label} · ${relativeTime}`;

  return (
    <div class="container" style={{ display: 'flex' }}>
      {/* Hero header */}
      <div class="tg-detail-header">
        <div
          class="tg-detail-header-icon"
          style={{ backgroundColor: visuals.bg, color: visuals.color }}
        >
          {isActive ? (
            <svg class="spinner-ios" style={{ width: '28px', height: '28px' }} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <circle cx="12" cy="12" r="10" stroke="var(--tg-color-divider)" stroke-width="2.5" />
              <path d="M12 2C6.47715 2 2 6.47715 2 12" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" />
            </svg>
          ) : (
            <visuals.Icon size={28} strokeWidth={2} />
          )}
        </div>
        <span class="tg-detail-header-title">{label}</span>
        <span class="tg-detail-header-subtitle">{headerSubtitle}</span>
      </div>

      {/* Build Information section */}
      <div class="tg-section">
        <div class="tg-section-header">Build Information</div>
        <div class="tg-list">
          {result && (
            <div class="tg-kv-row">
              <span class="tg-kv-label">Status</span>
              <span class={`tg-result-badge ${result}`}>{result}</span>
            </div>
          )}
          <div class="tg-kv-row">
            <span class="tg-kv-label"><GitBranch size={15} style={{ verticalAlign: '-2px', marginRight: '4px' }} />Branch</span>
            <span class="tg-kv-value mono">{ref}</span>
          </div>
          {commitHash && (
            <div class="tg-kv-row">
              <span class="tg-kv-label"><Hash size={15} style={{ verticalAlign: '-2px', marginRight: '4px' }} />Commit</span>
              <span class="tg-kv-value mono">{commitHash.substring(0, 7)}</span>
            </div>
          )}
          {duration !== null && duration > 0 && (
            <div class="tg-kv-row">
              <span class="tg-kv-label"><Timer size={15} style={{ verticalAlign: '-2px', marginRight: '4px' }} />Duration</span>
              <span class="tg-kv-value">{formatDuration(duration)}</span>
            </div>
          )}
          {fileSize > 0 && (
            <div class="tg-kv-row">
              <span class="tg-kv-label"><HardDrive size={15} style={{ verticalAlign: '-2px', marginRight: '4px' }} />APK Size</span>
              <span class="tg-kv-value">{formatFileSize(fileSize)}</span>
            </div>
          )}
          {triggeredBy && (
            <div class="tg-kv-row">
              <span class="tg-kv-label"><User size={15} style={{ verticalAlign: '-2px', marginRight: '4px' }} />Triggered by</span>
              <span class="tg-kv-value">{triggeredBy}</span>
            </div>
          )}
          <div class="tg-kv-row">
            <span class="tg-kv-label"><Calendar size={15} style={{ verticalAlign: '-2px', marginRight: '4px' }} />Started</span>
            <span class="tg-kv-value">{formatTimestamp(triggeredAt)}</span>
          </div>
          {completedAt && (
            <div class="tg-kv-row">
              <span class="tg-kv-label"><CalendarCheck size={15} style={{ verticalAlign: '-2px', marginRight: '4px' }} />Completed</span>
              <span class="tg-kv-value">{formatTimestamp(completedAt)}</span>
            </div>
          )}
        </div>
      </div>

      {/* Actions section (success builds with download URL) */}
      {result === 'success' && downloadUrl && (
        <div class="tg-section">
          <div class="tg-section-header">Actions</div>
          <div class="tg-list">
            <button class="tg-action-row" onClick={handleCopyLink}>
              <Copy size={20} />
              <span>Copy Download Link</span>
            </button>
            <a
              class="tg-action-row"
              href={downloadUrl}
              target="_blank"
              rel="noopener noreferrer"
              style={{ textDecoration: 'none' }}
            >
              <Download size={20} />
              <span>Download APK</span>
            </a>
          </div>
        </div>
      )}

      {/* Diagnostics section */}
      <div class="tg-section">
        <div class="tg-section-header">Diagnostics</div>
        <div class="tg-list">
          <div class="tg-kv-row">
            <span class="tg-kv-label"><FileText size={15} style={{ verticalAlign: '-2px', marginRight: '4px' }} />Request ID</span>
            <span class="tg-kv-value mono">{requestId}</span>
          </div>
        </div>
      </div>

      {/* Browser fallback cancel button (hidden in Telegram — uses MainButton) */}
      {canCancel && !isTelegram && (
        <div style={{ marginTop: 'auto', paddingTop: '16px', width: '100%' }}>
          <button
            class="tg-primary-button"
            style={{ backgroundColor: '#ff3b30' }}
            disabled={cancelling}
            onClick={handleCancel}
          >
            {cancelling ? (
              <svg class="spinner-ios" style={{ color: '#ffffff', width: '20px', height: '20px' }} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="12" cy="12" r="10" stroke="rgba(255,255,255,0.15)" stroke-width="3" />
                <path d="M12 2C6.47715 2 2 6.47715 2 12" stroke="currentColor" stroke-width="3" stroke-linecap="round" />
              </svg>
            ) : (
              <span>Cancel Build</span>
            )}
          </button>
        </div>
      )}
    </div>
  );
}
