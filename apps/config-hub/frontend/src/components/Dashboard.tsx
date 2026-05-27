/**
 * Dashboard — Service status grid with summary bar.
 *
 * Composes ServiceCard components in a 2-column grid.
 * Shows Drive connection or ephemeral banner based on storage backend.
 */

import { useCallback, useEffect, useState } from 'preact/hooks';
import { API } from '../api';
import { useSSE } from '../hooks/useSSE';
import ServiceCard from './ServiceCard';
import DriveCard from './DriveCard';
import EphemeralBanner from './EphemeralBanner';
import type { DriveStatus, ServiceStatuses } from '../types';
import type { TabId } from './Sidebar';

interface DashboardProps {
  statuses: ServiceStatuses | null;
  onStatusUpdate: (statuses: ServiceStatuses) => void;
  onNavigate: (tab: TabId) => void;
}

type HealthState = 'running' | 'stopped' | 'needs-config' | 'offline';

function healthState(status: { configured: boolean; running: boolean } | null): HealthState {
  if (!status) return 'offline';
  if (!status.configured) return 'needs-config';
  if (!status.running) return 'stopped';
  return 'running';
}

const SERVICE_LIST: { scope: 'bot' | 'builds' | 'agent' | 'file_manager'; label: string }[] = [
  { scope: 'bot', label: 'Telegram Bot' },
  { scope: 'builds', label: 'Build Manager' },
  { scope: 'agent', label: 'Jenkins Agent' },
  { scope: 'file_manager', label: 'File Manager' },
];

export default function Dashboard({
  statuses,
  onStatusUpdate,
  onNavigate,
}: DashboardProps) {
  const [driveStatus, setDriveStatus] = useState<DriveStatus | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<string>('');

  // SSE stream for real-time status updates
  const handleSSE = useCallback(
    (data: ServiceStatuses) => {
      onStatusUpdate(data);
      setLastRefreshed(new Date().toLocaleTimeString());
    },
    [onStatusUpdate],
  );

  useSSE<ServiceStatuses>('/api/services/stream', handleSSE, {
    eventName: 'status',
  });

  // Initial fetch + Drive status
  useEffect(() => {
    async function load() {
      const [statusResult, driveResult] = await Promise.all([
        API.getServiceStatus(),
        API.getDriveStatus(),
      ]);
      if (statusResult) {
        onStatusUpdate(statusResult);
        setLastRefreshed(new Date().toLocaleTimeString());
      }
      setDriveStatus(driveResult);
    }
    load();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function refreshAll() {
    const [statusResult, driveResult] = await Promise.all([
      API.getServiceStatus(),
      API.getDriveStatus(),
    ]);
    if (statusResult) {
      onStatusUpdate(statusResult);
      setLastRefreshed(new Date().toLocaleTimeString());
    }
    setDriveStatus(driveResult);
  }

  async function refreshDrive() {
    const result = await API.getDriveStatus();
    setDriveStatus(result);
  }

  // Summary bar
  let summaryText = '';
  let summaryClass = 'summary-bar--offline';
  if (statuses) {
    const entries = Object.values(statuses);
    const total = entries.length;
    const running = entries.filter((s) => healthState(s) === 'running').length;
    const offline = entries.filter((s) => healthState(s) === 'offline').length;

    if (running === total) {
      summaryText = `${total}/${total} services running`;
      summaryClass = 'summary-bar--ok';
    } else if (offline === total) {
      summaryText = 'All services offline';
      summaryClass = 'summary-bar--offline';
    } else {
      const issues = total - running;
      summaryText = `${running}/${total} running — ${issues} need${issues === 1 ? 's' : ''} attention`;
      summaryClass = 'summary-bar--warn';
    }
  }

  // Update document title with health indicator
  useEffect(() => {
    if (!statuses) return;
    const entries = Object.values(statuses);
    const allRunning = entries.every((s) => healthState(s) === 'running');
    const allOffline = entries.every((s) => healthState(s) === 'offline');
    const prefix = allRunning ? '●' : allOffline ? '○' : '◐';
    document.title = `${prefix} Stack Control`;
  }, [statuses]);

  const isEphemeral = driveStatus?.backend === 'ephemeral';

  return (
    <div>
      <h2 class="panel-title">Service Dashboard</h2>
      <p class="panel-desc">
        Real-time health monitoring for all stack services. Use the controls to
        start, stop, or restart individual services.
      </p>

      <div class="summary-bar">
        <span class={`summary-text ${summaryClass}`}>{summaryText}</span>
        {lastRefreshed && (
          <span class="last-refreshed">Updated {lastRefreshed}</span>
        )}
      </div>

      <div class="status-grid">
        {SERVICE_LIST.map(({ scope, label }) => (
          <ServiceCard
            key={scope}
            scope={scope}
            label={label}
            status={statuses?.[scope] ?? null}
            onRefresh={refreshAll}
            onNavigate={onNavigate}
          />
        ))}
      </div>

      {/* Storage backend UI */}
      {isEphemeral ? (
        <EphemeralBanner />
      ) : (
        <DriveCard driveStatus={driveStatus} onRefresh={refreshDrive} />
      )}
    </div>
  );
}
