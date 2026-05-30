/**
 * HomeScreen — Main navigation hub and service dashboard.
 *
 * Replaces the old Sidebar + ServicesPanel desktop layout with a
 * mobile-first Telegram-style screen. Lists service statuses in a
 * grouped card grid, followed by navigable config sections and tools.
 */

import { useCallback, useEffect, useState } from 'preact/hooks';
import { API } from '../api';
import ServiceCard from './ServiceCard';
import DriveCard from './DriveCard';
import StorageBanner from './StorageBanner';
import VpnWidget from './VpnWidget';
import type { DriveStatus, ServiceStatuses, Scope } from '../types';
import { healthState } from '../utils';
import type { Screen } from '../App';
import { Scaffold, List, ListItem, Badge } from 'tg-ui-preact';

interface HomeScreenProps {
  statuses: ServiceStatuses | null;
  onStatusUpdate: (statuses: ServiceStatuses) => void;
  onNavigate: (screen: Screen) => void;
  version: string | null;
  githubUrl: string | null;
  dirtyScopes?: Record<Scope, boolean>;
}

/** Inline GitHub SVG — Lucide 1.x removed brand icons for legal reasons. */
function GithubIcon({ size = 16, class: cls }: { size?: number; class?: string }) {
  return (
    <svg class={cls} width={size} height={size} viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
    </svg>
  );
}

const SERVICE_LIST: { scope: Scope; label: string }[] = [
  { scope: 'bot', label: 'Telegram Bot' },
  { scope: 'builds', label: 'Build Manager' },
  { scope: 'agent', label: 'Jenkins Agent' },
  { scope: 'file_manager', label: 'File Manager' },
];

const CONFIG_SECTIONS: { id: string; label: string; description: string; scopes: Scope[] }[] = [
  { id: 'telegram', label: 'Telegram', description: 'Bot identity & permissions', scopes: ['bot'] },
  { id: 'jenkins', label: 'Jenkins', description: 'Agent, builds & VPN', scopes: ['agent', 'builds'] },
  { id: 'storage', label: 'Storage', description: 'File backend & Drive', scopes: ['file_manager'] },
];

/** Aggregate multiple service statuses into a single health state. */
function aggregateHealth(statuses: ServiceStatuses | null, scopes: Scope[]): string {
  if (!statuses) return 'offline';
  const states = scopes.map(s => healthState(statuses[s]));
  if (states.every(s => s === 'running')) return 'running';
  if (states.some(s => s === 'needs-config')) return 'needs-config';
  if (states.some(s => s === 'stopped')) return 'stopped';
  return 'offline';
}

export default function HomeScreen({
  statuses,
  onStatusUpdate,
  onNavigate,
  version,
  githubUrl,
  dirtyScopes,
}: HomeScreenProps) {
  const [driveStatus, setDriveStatus] = useState<DriveStatus | null>(null);

  // Initial fetch + 5-second short polling interval
  useEffect(() => {
    async function load() {
      const [statusResult, driveResult] = await Promise.all([
        API.getServiceStatus(),
        API.getDriveStatus(),
      ]);
      if (statusResult) onStatusUpdate(statusResult);
      setDriveStatus(driveResult);
    }
    load();

    const interval = setInterval(async () => {
      const statusResult = await API.getServiceStatus();
      if (statusResult) onStatusUpdate(statusResult);
    }, 5000);

    return () => clearInterval(interval);
  }, [onStatusUpdate]);

  const refreshAll = useCallback(async () => {
    const [statusResult, driveResult] = await Promise.all([
      API.getServiceStatus(),
      API.getDriveStatus(),
    ]);
    if (statusResult) onStatusUpdate(statusResult);
    setDriveStatus(driveResult);
  }, [onStatusUpdate]);

  const refreshDrive = useCallback(async () => {
    const result = await API.getDriveStatus();
    setDriveStatus(result);
  }, []);

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

  const headerActions = (
    <div class="header-right" style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-xs)' }}>
      {version && <span class="version-badge loaded">v{version}</span>}
      {githubUrl && (
        <a class="github-link" href={githubUrl} target="_blank" rel="noopener">
          <GithubIcon class="github-icon" size={14} />
          GitHub
        </a>
      )}
    </div>
  );

  return (
    <Scaffold
      title="Stack Control"
      subtitle="Service monitoring & configuration"
      headerActions={headerActions}
    >

      {/* Service Dashboard */}
      <div class="tg-section">
        <h2 class="tg-section-header">Services</h2>
      </div>

      <div class="summary-bar">
        <span class={`summary-text ${summaryClass}`}>{summaryText}</span>
      </div>

      <div class="status-grid">
        {SERVICE_LIST.map(({ scope, label }) => (
          <ServiceCard
            key={scope}
            scope={scope}
            label={label}
            status={statuses?.[scope] ?? null}
            onRefresh={refreshAll}
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

      {/* Configuration Sections */}
      <List header="Configuration">
        {CONFIG_SECTIONS.map(({ id, label, description, scopes }) => {
          const state = aggregateHealth(statuses, scopes);
          const isSectionDirty = dirtyScopes ? scopes.some(s => dirtyScopes[s]) : false;
          
          const badgeVariant = state === 'running' ? 'success'
            : state === 'needs-config' ? 'warning'
            : state === 'stopped' ? 'info'
            : 'neutral';

          return (
            <ListItem
              key={id}
              title={
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--space-xs)' }}>
                  {label}
                  {isSectionDirty && (
                    <span
                      className="save-dot"
                      style={{
                        display: 'inline-block',
                        opacity: 1,
                        transform: 'scale(1)',
                        animation: 'pulseGlow 1.8s infinite alternate',
                        marginLeft: 0,
                      }}
                    />
                  )}
                </span>
              }
              subtitle={description}
              rightElement={
                <Badge variant={badgeVariant}>
                  {state === 'needs-config' ? 'Needs config' : state}
                </Badge>
              }
              onClick={() => onNavigate({ screen: 'config', id })}
            />
          );
        })}
      </List>

      {/* Tools */}
      <List header="Tools">
        <ListItem
          title="Pipeline Generator"
          subtitle="Generate ready-to-use Jenkinsfile scripts"
          onClick={() => onNavigate({ screen: 'jenkinsfile' })}
        />
        <ListItem
          title="Config Transfer"
          subtitle="Backup and restore configuration files"
          onClick={() => onNavigate({ screen: 'transfer' })}
        />
      </List>
    </Scaffold>
  );
}
