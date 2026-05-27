/**
 * Sidebar — Tab navigation with service health dots.
 *
 * Renders the vertical sidebar (desktop) / horizontal tabs (mobile).
 * Shows health dots per-service based on live status.
 */

import { LayoutDashboard } from 'lucide-preact';
import type { Scope, ServiceStatus, ServiceStatuses } from '../types';

export type TabId = Scope | 'dashboard' | 'jenkinsfile' | 'export';

interface SidebarProps {
  activeTab: TabId;
  onTabChange: (tab: TabId) => void;
  statuses: ServiceStatuses | null;
}

const SERVICE_TABS: { id: Scope; label: string }[] = [
  { id: 'bot', label: 'Telegram Bot' },
  { id: 'builds', label: 'Build Manager' },
  { id: 'agent', label: 'Jenkins Agent' },
  { id: 'file_manager', label: 'File Manager' },
];

const TOOL_TABS: { id: TabId; label: string }[] = [
  { id: 'jenkinsfile', label: 'Jenkins Pipeline' },
  { id: 'export', label: 'Config Transfer' },
];

function healthState(status: ServiceStatus | null): string {
  if (!status) return 'offline';
  if (!status.configured) return 'needs-config';
  if (!status.running) return 'stopped';
  return 'running';
}

export default function Sidebar({
  activeTab,
  onTabChange,
  statuses,
}: SidebarProps) {
  return (
    <nav class="sidebar" role="tablist">
      {/* Dashboard */}
      <button
        class={`sidebar-btn sidebar-btn--primary${activeTab === 'dashboard' ? ' active' : ''}`}
        onClick={() => onTabChange('dashboard')}
        role="tab"
        aria-selected={activeTab === 'dashboard'}
      >
        <LayoutDashboard class="sidebar-icon" size={16} />
        Dashboard
      </button>

      <div class="sidebar-divider" />
      <span class="sidebar-label">Configuration</span>

      {SERVICE_TABS.map(({ id, label }) => {
        const state = statuses ? healthState(statuses[id]) : 'offline';
        return (
          <button
            key={id}
            class={`sidebar-btn${activeTab === id ? ' active' : ''}`}
            onClick={() => onTabChange(id)}
            role="tab"
            aria-selected={activeTab === id}
          >
            {label}
            <span class={`sidebar-dot sidebar-dot--${state}`} />
          </button>
        );
      })}

      <div class="sidebar-divider" />
      <span class="sidebar-label">Tools</span>

      {TOOL_TABS.map(({ id, label }) => (
        <button
          key={id}
          class={`sidebar-btn${activeTab === id ? ' active' : ''}`}
          onClick={() => onTabChange(id)}
          role="tab"
          aria-selected={activeTab === id}
        >
          {label}
        </button>
      ))}
    </nav>
  );
}
