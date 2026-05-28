/**
 * Sidebar — Tab navigation with service health dots.
 *
 * Renders a vertical sidebar (desktop) / horizontal tabs (mobile).
 * Shows health dots per-section based on live status.
 *
 * Sections:
 *   OPERATIONS: Services (dashboard)
 *   CONFIGURATION: Telegram (bot), Jenkins (agent + builds), Storage (file_manager)
 *   TOOLS: Tools (jenkinsfile + config transfer)
 */

import { LayoutDashboard, Wrench } from 'lucide-preact';
import type { Scope, ServiceStatus, ServiceStatuses } from '../types';

export type SectionId = 'services' | 'telegram' | 'jenkins' | 'storage' | 'tools';

interface SidebarProps {
  activeTab: SectionId;
  onTabChange: (tab: SectionId) => void;
  statuses: ServiceStatuses | null;
  dirtyScopes?: Record<Scope, boolean>;
}

/** Resolve health state from a service status object. */
function healthState(status: ServiceStatus | null): string {
  if (!status) return 'offline';
  if (!status.configured) return 'needs-config';
  if (!status.running) return 'stopped';
  return 'running';
}

/** Aggregate multiple service statuses into a single health state. */
function aggregateHealth(statuses: ServiceStatuses | null, scopes: Scope[]): string {
  if (!statuses) return 'offline';
  const states = scopes.map(s => healthState(statuses[s]));
  if (states.every(s => s === 'running')) return 'running';
  if (states.some(s => s === 'needs-config')) return 'needs-config';
  if (states.some(s => s === 'stopped')) return 'stopped';
  return 'offline';
}

/** Configuration sections — each maps to one or more backend scopes. */
const CONFIG_SECTIONS: {
  id: SectionId;
  label: string;
  scopes: Scope[];
}[] = [
  { id: 'telegram', label: 'Telegram', scopes: ['bot'] },
  { id: 'jenkins', label: 'Jenkins', scopes: ['agent', 'builds'] },
  { id: 'storage', label: 'Storage', scopes: ['file_manager'] },
];

export default function Sidebar({
  activeTab,
  onTabChange,
  statuses,
  dirtyScopes,
}: SidebarProps) {
  return (
    <nav class="sidebar" role="tablist">
      {/* Operations */}
      <span class="sidebar-label">Operations</span>
      <button
        class={`sidebar-btn sidebar-btn--primary${activeTab === 'services' ? ' active' : ''}`}
        onClick={() => onTabChange('services')}
        role="tab"
        aria-selected={activeTab === 'services'}
      >
        <LayoutDashboard class="sidebar-icon" size={16} />
        Services
      </button>

      <div class="sidebar-divider" />
      <span class="sidebar-label">Configuration</span>

      {CONFIG_SECTIONS.map(({ id, label, scopes }) => {
        const state = aggregateHealth(statuses, scopes);
        const isDirty = scopes.some(s => !!dirtyScopes?.[s]);
        return (
          <button
            key={id}
            class={`sidebar-btn${activeTab === id ? ' active' : ''}`}
            onClick={() => onTabChange(id)}
            role="tab"
            aria-selected={activeTab === id}
          >
            {label}
            <div class="sidebar-status-container">
              {isDirty && <span class="sidebar-unsaved-badge">Unsaved</span>}
              <span class={`sidebar-dot sidebar-dot--${state}`} />
            </div>
          </button>
        );
      })}

      <div class="sidebar-divider" />
      <span class="sidebar-label">Tools</span>

      <button
        class={`sidebar-btn${activeTab === 'tools' ? ' active' : ''}`}
        onClick={() => onTabChange('tools')}
        role="tab"
        aria-selected={activeTab === 'tools'}
      >
        <Wrench class="sidebar-icon" size={16} />
        Tools
      </button>
    </nav>
  );
}
