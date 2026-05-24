/* Dashboard tab — status cards, drive status, and polling. */

import { Icons } from './icons.js';
import { API } from './api.js';
import { Toast } from './toast.js';
import { showConfirm } from './confirm.js';

/** Human-readable labels for each service key. */
const SERVICE_LABELS = {
  bot: 'Telegram Bot',
  builds: 'Build Manager',
  agent: 'Jenkins Agent',
  file_manager: 'File Manager',
};

/** Scope mapping: service key → sidebar tab id for "Configure →" links. */
const SERVICE_TAB_MAP = {
  bot: 'bot',
  builds: 'builds',
  agent: 'agent',
  file_manager: 'file_manager',
};

/** Small SVG icons for each service card header. */
const SERVICE_ICONS = {
  bot: '<svg class="status-icon" viewBox="0 0 20 20" fill="currentColor"><path d="M10 2a2 2 0 00-2 2v1H6a3 3 0 00-3 3v6a3 3 0 003 3h8a3 3 0 003-3V8a3 3 0 00-3-3h-2V4a2 2 0 00-2-2zm-2 8a1 1 0 112 0 1 1 0 01-2 0zm5-1a1 1 0 100 2 1 1 0 000-2z"/></svg>',
  builds: '<svg class="status-icon" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M5.5 3A2.5 2.5 0 003 5.5v9A2.5 2.5 0 005.5 17h9a2.5 2.5 0 002.5-2.5v-9A2.5 2.5 0 0014.5 3h-9zM8 7a1 1 0 000 2h4a1 1 0 100-2H8zm0 4a1 1 0 100 2h4a1 1 0 100-2H8z" clip-rule="evenodd"/></svg>',
  agent: '<svg class="status-icon" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M7.84 1.804A1 1 0 018.82 1h2.36a1 1 0 01.98.804l.331 1.652a6.993 6.993 0 011.929 1.115l1.598-.54a1 1 0 011.186.447l1.18 2.044a1 1 0 01-.205 1.251l-1.267 1.113a7.047 7.047 0 010 2.228l1.267 1.113a1 1 0 01.206 1.25l-1.18 2.045a1 1 0 01-1.187.447l-1.598-.54a6.993 6.993 0 01-1.929 1.115l-.33 1.652a1 1 0 01-.98.804H8.82a1 1 0 01-.98-.804l-.331-1.652a6.993 6.993 0 01-1.929-1.115l-1.598.54a1 1 0 01-1.186-.447l-1.18-2.044a1 1 0 01.205-1.251l1.267-1.114a7.05 7.05 0 010-2.227L1.821 7.773a1 1 0 01-.206-1.25l1.18-2.045a1 1 0 011.187-.447l1.598.54A6.992 6.992 0 017.51 3.456l.33-1.652zM10 13a3 3 0 100-6 3 3 0 000 6z" clip-rule="evenodd"/></svg>',
  file_manager: '<svg class="status-icon" viewBox="0 0 20 20" fill="currentColor"><path d="M3.75 3A1.75 1.75 0 002 4.75v3.26a3.235 3.235 0 011.75-.51h12.5c.644 0 1.245.188 1.75.51V6.75A1.75 1.75 0 0016.25 5h-4.836a.25.25 0 01-.177-.073L9.823 3.513A1.75 1.75 0 008.586 3H3.75zM3.75 9A1.75 1.75 0 002 10.75v4.5c0 .966.784 1.75 1.75 1.75h12.5A1.75 1.75 0 0018 15.25v-4.5A1.75 1.75 0 0016.25 9H3.75z"/></svg>',
};

/**
 * Derive one of exactly four mutually-exclusive health states:
 *   offline       — service did not respond
 *   needs-config  — service responded but config validation failed
 *   stopped       — service is configured but not running
 *   running       — service is responding, configured, and running
 */
function serviceHealthState(status) {
  if (status.available === false) return 'offline';
  if (!status.configured)         return 'needs-config';
  if (!status.running)            return 'stopped';
  return 'running';
}

function badgeClass(state) {
  const map = {
    'offline': 'badge--offline',
    'needs-config': 'badge--awaiting',
    'stopped': 'badge--stopped',
    'running': 'badge--running',
  };
  return map[state] || 'badge--offline';
}

function badgeLabel(state) {
  const map = {
    'offline': 'Offline',
    'needs-config': 'Needs configuration',
    'stopped': 'Stopped',
    'running': 'Running',
  };
  return map[state] || 'Unknown';
}

/** Format a UNIX epoch timestamp as relative uptime. */
function formatUptime(startedAt) {
  if (!startedAt) return null;
  const seconds = Math.floor(Date.now() / 1000 - startedAt);
  if (seconds < 0) return null;
  if (seconds < 60)   return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

/** Build the service-specific detail lines for a card. */
function buildDetails(key, status, state) {
  const details = [];

  // Running services: show uptime
  if (state === 'running') {
    const uptime = formatUptime(status.started_at);
    if (uptime) details.push(`Uptime: ${uptime}`);
  }

  // Service-specific operational data
  if (status.pending_builds !== undefined)
    details.push(`Pending builds: ${status.pending_builds}`);
  if (status.agent_name)
    details.push(`Agent: ${status.agent_name}`);
  if (status.pid)
    details.push(`PID: ${status.pid}`);

  return details;
}

function renderServiceCard(name, key, status) {
  const state = serviceHealthState(status);
  const cls = badgeClass(state);
  const label = badgeLabel(state);
  const icon = SERVICE_ICONS[key] || '';

  // Service-specific details
  const details = buildDetails(key, status, state);
  let detailsHtml = '';
  if (details.length) {
    detailsHtml = `<div class="status-details">${details.map((d) => `<p>${d}</p>`).join('')}</div>`;
  }

  // Config error callout (only when config validation fails)
  let errorHtml = '';
  if (status.config_error && state === 'needs-config') {
    errorHtml = `<div class="config-error-callout">${status.config_error}</div>`;
  }

  // Generic last_error (only when there's no config_error already shown and not offline)
  const error = status.last_error ?? status.detail ?? null;
  if (error && error !== 'none' && state !== 'offline' && !status.config_error) {
    errorHtml = `<div class="config-error-callout">${error}</div>`;
  }

  // "Configure →" link for needs-config state
  let configureLink = '';
  if (state === 'needs-config') {
    const tabId = SERVICE_TAB_MAP[key] || key;
    configureLink = `<a class="configure-link" onclick="switchTab('${tabId}')">Configure →</a>`;
  }

  // Button logic per state
  const canStart   = state === 'stopped';
  const canRestart = state === 'running';
  const canStop    = state === 'running';

  return `
    <div class="card status-card status-card--${state}" id="card-${key}">
      <div class="status-header">
        <h3>${icon}${name}</h3>
        <span class="badge ${cls}">${label}</span>
      </div>
      ${detailsHtml}
      ${errorHtml}
      ${configureLink}
      <div class="status-controls">
        <button
          class="btn btn-accent btn-sm"
          onclick="controlService('${key}','${canRestart ? 'restart' : 'start'}')"
          ${(!canStart && !canRestart) ? 'disabled' : ''}>
          ${canRestart
            ? `${Icons.restart}Restart`
            : `${Icons.play}Start`}
        </button>
        <button
          class="btn btn-danger btn-sm"
          onclick="handleStop('${key}')"
          ${!canStop ? 'disabled' : ''}>
          ${Icons.stop}Stop
        </button>
      </div>
    </div>`;
}

/** Render the summary bar above the status grid. */
function renderSummaryBar(statuses) {
  const entries = Object.entries(statuses);
  const total = entries.length;
  const counts = { running: 0, stopped: 0, 'needs-config': 0, offline: 0 };

  for (const [, s] of entries) {
    const state = serviceHealthState(s);
    counts[state] = (counts[state] || 0) + 1;
  }

  let summaryText;
  let summaryClass;

  if (counts.running === total) {
    summaryText = `${total}/${total} services running`;
    summaryClass = 'summary-bar--ok';
  } else if (counts.offline === total) {
    summaryText = 'All services offline';
    summaryClass = 'summary-bar--offline';
  } else {
    const issues = total - counts.running;
    summaryText = `${counts.running}/${total} running — ${issues} need${issues === 1 ? 's' : ''} attention`;
    summaryClass = 'summary-bar--warn';
  }

  return `<span class="summary-text ${summaryClass}">${summaryText}</span>`;
}

/** Update sidebar health dots based on current service statuses. */
function updateSidebarDots(statuses) {
  const dotMap = { bot: 'bot', builds: 'builds', agent: 'agent', file_manager: 'file_manager' };
  for (const [key, tabId] of Object.entries(dotMap)) {
    const btn = document.querySelector(`.sidebar-btn[data-tab="${tabId}"]`);
    if (!btn || !statuses[key]) continue;

    const state = serviceHealthState(statuses[key]);
    let dot = btn.querySelector('.sidebar-dot');
    if (!dot) {
      dot = document.createElement('span');
      dot.className = 'sidebar-dot';
      btn.appendChild(dot);
    }
    dot.className = `sidebar-dot sidebar-dot--${state}`;
  }
}

/** Update document title with health indicator. */
function updateTitleHealth(statuses) {
  const entries = Object.values(statuses);
  const allRunning = entries.every(s => serviceHealthState(s) === 'running');
  const allOffline = entries.every(s => serviceHealthState(s) === 'offline');

  let prefix;
  if (allRunning) prefix = '●';
  else if (allOffline) prefix = '○';
  else prefix = '◐';

  document.title = `${prefix} Stack Control`;
}

export async function refreshDriveCard() {
  const drive = await API.getDriveStatus();
  const el = document.getElementById('drive-status-detail');
  const toggleBtn = document.getElementById('drive-connect-toggle');
  const disconnectBtn = document.getElementById('drive-disconnect');

  if (!drive) {
    el.textContent = 'Unable to check Drive status.';
    toggleBtn.disabled = true;
    disconnectBtn.disabled = true;
    return;
  }

  if (!drive.configured) {
    el.textContent = 'OAuth credentials not configured. Enter your Client ID and Secret above, then save.';
    toggleBtn.innerHTML = `${Icons.cloud}Connect Google Drive`;
    toggleBtn.disabled = true;
    disconnectBtn.disabled = true;
  } else if (drive.connected) {
    el.innerHTML = `<span class="text-success">Connected</span> — Token: ${drive.token_path}`;
    toggleBtn.innerHTML = `${Icons.restart}Change Account`;
    toggleBtn.disabled = false;
    disconnectBtn.disabled = false;
  } else {
    el.textContent = 'Not connected. Click "Connect Google Drive" to authorize.';
    toggleBtn.innerHTML = `${Icons.cloud}Connect Google Drive`;
    toggleBtn.disabled = false;
    disconnectBtn.disabled = true;
  }
}

export async function refreshDashboard(status) {
  if (!status) {
    status = await API.getServiceStatus();
  }

  if (status) {
    // Update summary bar
    const summaryEl = document.getElementById('summary-bar');
    if (summaryEl) summaryEl.innerHTML = renderSummaryBar(status);

    // Update status cards
    document.getElementById('status-grid').innerHTML =
      renderServiceCard('Telegram Bot', 'bot', status.bot) +
      renderServiceCard('Build Manager', 'builds', status.builds) +
      renderServiceCard('Jenkins Agent', 'agent', status.agent) +
      renderServiceCard('File Manager', 'file_manager', status.file_manager);

    // Update sidebar dots and title
    updateSidebarDots(status);
    updateTitleHealth(status);
  }

  // Update last-refreshed timestamp
  const tsEl = document.getElementById('last-refreshed');
  if (tsEl) tsEl.textContent = `Updated ${new Date().toLocaleTimeString()}`;
}

/** Stop handler with confirmation modal. */
export async function handleStop(service) {
  const label = SERVICE_LABELS[service] || service;
  const confirmed = await showConfirm({
    title: `Stop ${label}?`,
    message: 'This will interrupt any active operations. The service can be restarted from the dashboard.',
    confirmLabel: 'Stop',
    danger: true,
  });
  if (confirmed) {
    await controlService(service, 'stop');
  }
}

export async function controlService(service, action) {
  // Disable buttons on the card during the operation
  const card = document.getElementById(`card-${service}`);
  const btns = card ? card.querySelectorAll('.btn') : [];
  btns.forEach((b) => { b.disabled = true; });

  const result = await API.controlService(service, action);
  if (result) {
    const label = SERVICE_LABELS[service] || service;
    const verb = action.charAt(0).toUpperCase() + action.slice(1);
    Toast.show(`${label}: ${verb} command sent`, 'info');
    await refreshDashboard();
  } else {
    // Re-enable buttons on failure
    btns.forEach((b) => { b.disabled = false; });
  }
}

/* SSE Stream manager */
export const Poller = {
  _eventSource: null,
  _fn: null,

  start(fn) {
    this.stop();
    this._fn = fn;
    
    // Snappy initial load via HTTP fetch before the stream connects
    fn();

    this._connect();

    // Reconnect/disconnect when browser tab visibility changes
    document.addEventListener('visibilitychange', this._onVisibility);
  },

  stop() {
    this._disconnect();
    document.removeEventListener('visibilitychange', this._onVisibility);
    this._fn = null;
  },

  _connect() {
    if (this._eventSource) return;

    this._eventSource = new EventSource('/api/services/stream');

    this._eventSource.addEventListener('status', (event) => {
      try {
        const status = JSON.parse(event.data);
        if (this._fn) {
          this._fn(status);
        }
      } catch (err) {
        console.error('Failed to parse service status SSE payload:', err);
      }
    });

    this._eventSource.onerror = (err) => {
      console.error('Service status SSE connection error/closed. Retrying...', err);
    };
  },

  _disconnect() {
    if (this._eventSource) {
      this._eventSource.close();
      this._eventSource = null;
    }
  },

  _onVisibility() {
    if (document.hidden) {
      Poller._disconnect();
    } else {
      Poller._connect();
    }
  },
};
