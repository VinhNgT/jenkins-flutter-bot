/**
 * ServicesPanel — Service status grid with summary bar.
 *
 * Composes ServiceCard components in a 2-column grid.
 * Shows Drive connection or ephemeral banner based on storage backend.
 */

import { useEffect, useState } from 'preact/hooks';
import { API } from '../api';
import ServiceCard from './ServiceCard';
import DriveCard from './DriveCard';
import StorageBanner from './StorageBanner';
import VpnWidget from './VpnWidget';
import type { DriveStatus, ServiceStatuses } from '../types';
import type { SectionId } from './Sidebar';
import { healthState } from '../utils';

interface ServicesPanelProps {
  statuses: ServiceStatuses | null;
  onStatusUpdate: (statuses: ServiceStatuses) => void;
  onNavigate: (tab: SectionId) => void;
}

const SERVICE_LIST: { scope: 'bot' | 'builds' | 'agent' | 'file_manager'; label: string }[] = [
  { scope: 'bot', label: 'Telegram Bot' },
  { scope: 'builds', label: 'Build Manager' },
  { scope: 'agent', label: 'Jenkins Agent' },
  { scope: 'file_manager', label: 'File Manager' },
];

export default function ServicesPanel({
  statuses,
  onStatusUpdate,
  onNavigate,
}: ServicesPanelProps) {
  const [driveStatus, setDriveStatus] = useState<DriveStatus | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<string>('');

  // Initial fetch + 5-second short polling interval
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

    const interval = setInterval(async () => {
      const statusResult = await API.getServiceStatus();
      if (statusResult) {
        onStatusUpdate(statusResult);
        setLastRefreshed(new Date().toLocaleTimeString());
      }
    }, 5000);

    return () => clearInterval(interval);
  }, [onStatusUpdate]);

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
  const isLogOnly = driveStatus?.backend === 'log_only';

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

      <VpnWidget />

      {/* Storage backend UI */}
      {isEphemeral || isLogOnly ? (
        <StorageBanner mode={isLogOnly ? 'log_only' : 'ephemeral'} />
      ) : (
        <DriveCard driveStatus={driveStatus} onRefresh={refreshDrive} />
      )}
    </div>
  );
}
