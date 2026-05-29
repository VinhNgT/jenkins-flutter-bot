/**
 * ServiceCard — Individual service status card on the dashboard.
 *
 * Displays health state, uptime, errors, and start/stop/restart controls.
 */

import { Play, RotateCcw, Square } from 'lucide-preact';
import { useState } from 'preact/hooks';
import { API } from '../api';
import { useConfirm } from './ConfirmDialog';
import type { Scope, ServiceStatus } from '../types';
import type { SectionId } from './Sidebar';

interface ServiceCardProps {
  scope: Scope;
  label: string;
  status: ServiceStatus | null;
  onRefresh: () => void;
  onNavigate: (tab: SectionId) => void;
}

/** Map backend scope to its UI section. */
const SCOPE_TO_SECTION: Record<Scope, SectionId> = {
  bot: 'telegram',
  agent: 'jenkins',
  builds: 'jenkins',
  file_manager: 'storage',
};

type HealthState = 'running' | 'stopped' | 'needs-config' | 'offline';

function healthState(status: ServiceStatus | null): HealthState {
  if (!status) return 'offline';
  if (!status.configured) return 'needs-config';
  if (!status.running) return 'stopped';
  return 'running';
}

const BADGE_LABELS: Record<HealthState, string> = {
  running: 'Running',
  stopped: 'Stopped',
  'needs-config': 'Needs configuration',
  offline: 'Offline',
};

const BADGE_CLASSES: Record<HealthState, string> = {
  running: 'badge--running',
  stopped: 'badge--stopped',
  'needs-config': 'badge--awaiting',
  offline: 'badge--offline',
};

function formatUptime(startedAt?: number): string | null {
  if (!startedAt) return null;
  const seconds = Math.floor(Date.now() / 1000 - startedAt);
  if (seconds < 0) return null;
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

export default function ServiceCard({
  scope,
  label,
  status,
  onRefresh,
  onNavigate,
}: ServiceCardProps) {

  const confirm = useConfirm();
  const [busy, setBusy] = useState(false);

  const state = healthState(status);
  const canStart = state === 'stopped';
  const canRestart = state === 'running';
  const canStop = state === 'running';

  // Build detail lines
  const details: string[] = [];
  if (state === 'running' && status) {
    const uptime = formatUptime(status.started_at);
    if (uptime) details.push(`Uptime: ${uptime}`);
  }

  // Error display
  let errorText: string | null = null;
  if (status?.config_error && state === 'needs-config') {
    errorText = status.config_error;
  } else if (status?.last_error && status.last_error !== 'none' && state !== 'offline' && !status.config_error) {
    errorText = status.last_error;
  }

  async function handleControl(action: 'start' | 'stop' | 'restart') {
    if (action === 'stop') {
      const confirmed = await confirm({
        title: `Stop ${label}?`,
        message:
          'This will interrupt any active operations. The service can be restarted from the dashboard.',
        confirmLabel: 'Stop',
        danger: true,
      });
      if (!confirmed) return;
    }

    setBusy(true);
    const result = await API.controlService(scope, action);
    setBusy(false);

    if (result) {
      onRefresh();
    }
  }

  return (
    <div class={`card status-card status-card--${state}`} id={`card-${scope}`}>
      <div class="status-header">
        <h3>{label}</h3>
        <span class={`badge ${BADGE_CLASSES[state]}`}>{BADGE_LABELS[state]}</span>
      </div>

      {details.length > 0 && (
        <div class="status-details">
          {details.map((d) => (
            <p key={d}>{d}</p>
          ))}
        </div>
      )}

      {errorText && <div class="config-error-callout">{errorText}</div>}

      {state === 'needs-config' && (
        <a
          class="configure-link"
          onClick={() => onNavigate(SCOPE_TO_SECTION[scope])}
        >
          Configure →
        </a>
      )}

      <div class="status-controls">
        <button
          class="btn btn-accent btn-sm"
          disabled={busy || (!canStart && !canRestart)}
          onClick={() => handleControl(canRestart ? 'restart' : 'start')}
        >
          {canRestart ? (
            <>
              <RotateCcw class="icon" size={12} />
              Restart
            </>
          ) : (
            <>
              <Play class="icon" size={12} />
              Start
            </>
          )}
        </button>
        <button
          class="btn btn-danger btn-sm"
          disabled={busy || !canStop}
          onClick={() => handleControl('stop')}
        >
          <Square class="icon" size={12} />
          Stop
        </button>
      </div>
    </div>
  );
}
