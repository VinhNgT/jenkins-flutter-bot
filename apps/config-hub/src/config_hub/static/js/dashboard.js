/* Dashboard tab — status cards, drive status, and polling. */

function badgeClass(status) {
  if (status.available === false) return 'badge--unavailable';
  return status.running ? 'badge--running' : 'badge--stopped';
}

function badgeLabel(status) {
  if (status.available === false) return 'Unavailable';
  return status.running ? 'Running' : 'Stopped';
}

function renderServiceCard(name, key, status) {
  const cls = badgeClass(status);
  const label = badgeLabel(status);
  const details = [];

  if (status.drive_connected !== undefined)
    details.push(`Drive: ${status.drive_connected ? 'Connected' : 'No'}`);
  if (status.pending_builds !== undefined)
    details.push(`Pending builds: ${status.pending_builds}`);
  if (status.agent_name)
    details.push(`Agent: ${status.agent_name}`);
  if (status.pid)
    details.push(`PID: ${status.pid}`);

  const error = status.last_error ?? status.detail ?? null;
  if (error && error !== 'none' && status.available !== false) {
    details.push(`Error: ${error}`);
  }

  const detailsHtml = details.length
    ? `<div class="status-details">${details.map((d) => `<p>${d}</p>`).join('')}</div>`
    : '';

  const configuredBadge = status.configured === false
    ? `<span class="badge badge--not-configured">Not Configured</span>`
    : '';

  return `
    <div class="card status-card" id="card-${key}">
      <div class="status-header">
        <h3>${name}</h3>
        <div class="badge-group">
          ${configuredBadge}
          <span class="badge ${cls}">${label}</span>
        </div>
      </div>
      ${detailsHtml}
      <div class="status-controls">
        <button
          class="btn btn-accent btn-sm"
          onclick="controlService('${key}','${status.running ? 'restart' : 'start'}')"
          ${(!status.configured || status.available === false) ? 'disabled' : ''}>
          ${status.running
            ? `${Icons.restart}Restart`
            : `${Icons.play}Start`}
        </button>
        <button
          class="btn btn-danger btn-sm"
          onclick="controlService('${key}','stop')"
          ${(!status.running || status.available === false) ? 'disabled' : ''}>
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
