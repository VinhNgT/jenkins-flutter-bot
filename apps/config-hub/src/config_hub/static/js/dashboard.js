/* Dashboard tab — status cards, drive status, and polling. */

/**
 * Derive one of exactly three mutually-exclusive health states:
 *   offline            — service did not respond
 *   awaiting-config    — service responded but is not fully configured / not running
 *   running            — service is responding, configured, and running
 */
function serviceHealthState(status) {
  if (status.available === false) return 'offline';
  if (status.running && status.configured !== false) return 'running';
  return 'awaiting-config';
}

function badgeClass(status) {
  const state = serviceHealthState(status);
  if (state === 'offline')         return 'badge--offline';
  if (state === 'awaiting-config') return 'badge--awaiting';
  return 'badge--running';
}

function badgeLabel(status) {
  const state = serviceHealthState(status);
  if (state === 'offline')         return 'Offline';
  if (state === 'awaiting-config') return 'Awaiting configuration';
  return 'Running';
}

function renderServiceCard(name, key, status) {
  const cls = badgeClass(status);
  const label = badgeLabel(status);
  const state = serviceHealthState(status);
  const details = [];

  if (status.drive_connected !== undefined)
    details.push(`Drive: ${status.drive_connected ? 'Connected' : 'No'}`);
  if (status.pending_builds !== undefined)
    details.push(`Pending builds: ${status.pending_builds}`);
  if (status.agent_name)
    details.push(`Agent: ${status.agent_name}`);
  if (status.pid)
    details.push(`PID: ${status.pid}`);

  if (status.config_error && state === 'awaiting-config') {
    details.push(`${status.config_error}`);
  }

  const error = status.last_error ?? status.detail ?? null;
  if (error && error !== 'none' && state !== 'offline' && !status.config_error) {
    details.push(`Error: ${error}`);
  }

  const detailsHtml = details.length
    ? `<div class="status-details">${details.map((d) => `<p>${d}</p>`).join('')}</div>`
    : '';

  // Buttons: only enabled when the service can actually act on the command.
  const canStart   = state === 'awaiting-config' && status.configured !== false;
  const canRestart = state === 'running';
  const canStop    = state === 'running';

  return `
    <div class="card status-card" id="card-${key}">
      <div class="status-header">
        <h3>${name}</h3>
        <span class="badge ${cls}">${label}</span>
      </div>
      ${detailsHtml}
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
          onclick="controlService('${key}','stop')"
          ${!canStop ? 'disabled' : ''}>
          ${Icons.stop}Stop
        </button>
      </div>
    </div>`;
}

// eslint-disable-next-line no-unused-vars
async function refreshDriveCard() {
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

// eslint-disable-next-line no-unused-vars
async function refreshDashboard() {
  const status = await API.getServiceStatus();

  if (status) {
    document.getElementById('status-grid').innerHTML =
      renderServiceCard('Telegram Bot', 'bot', status.bot) +
      renderServiceCard('Build Manager', 'builds', status.builds) +
      renderServiceCard('Jenkins Agent', 'agent', status.agent) +
      renderServiceCard('File Manager', 'file_manager', status.file_manager);
  }

  await refreshDriveCard();
}

// eslint-disable-next-line no-unused-vars
async function controlService(service, action) {
  const result = await API.controlService(service, action);
  if (result) {
    Toast.show(`${service}: ${action} command sent`, 'info');
    await refreshDashboard();
  }
}

/* Polling manager */
// eslint-disable-next-line no-unused-vars
const Poller = {
  _interval: null,
  _fn: null,

  start(fn) {
    this.stop();
    this._fn = fn;
    fn(); // immediate first call
    this._interval = setInterval(fn, 5000);
  },

  stop() {
    if (this._interval) {
      clearInterval(this._interval);
      this._interval = null;
    }
    this._fn = null;
  },
};
