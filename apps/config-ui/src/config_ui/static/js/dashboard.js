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

  if (status.configured !== undefined)
    details.push(`Configured: ${status.configured ? 'Yes' : 'No'}`);
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

  return `
    <div class="card status-card" id="card-${key}">
      <div class="status-header">
        <h3>${name}</h3>
        <span class="badge ${cls}">${label}</span>
      </div>
      ${detailsHtml}
      <div class="status-controls">
        <button class="btn btn-accent btn-sm" onclick="controlService('${key}','start')"><svg class="icon" viewBox="0 0 20 20"><path d="M6.5 4.5v11l9-5.5z"/></svg>Start</button>
        <button class="btn btn-secondary btn-sm" onclick="controlService('${key}','restart')"><svg class="icon" viewBox="0 0 20 20"><path d="M4 10a6 6 0 0110.472-4.001L12.5 8H18V2l-2.052 2.052A8 8 0 1018 10h-2a6 6 0 01-12 0z"/></svg>Restart</button>
        <button class="btn btn-danger btn-sm" onclick="controlService('${key}','stop')"><svg class="icon" viewBox="0 0 20 20"><rect x="5" y="5" width="10" height="10" rx="1"/></svg>Stop</button>
      </div>
    </div>`;
}

// eslint-disable-next-line no-unused-vars
async function refreshDriveCard() {
  const drive = await API.getDriveStatus();
  const el = document.getElementById('drive-status-detail');
  const actionsEl = document.getElementById('drive-connect-actions');
  if (!drive) {
    el.textContent = 'Unable to check Drive status.';
    actionsEl.style.display = 'none';
    return;
  }

  if (!drive.configured) {
    el.textContent = 'OAuth credentials not configured. Go to the Google Drive tab to set up.';
    actionsEl.style.display = 'none';
  } else if (drive.connected) {
    el.innerHTML = `<span class="text-success">Connected</span> — Token: ${drive.token_path}`;
    actionsEl.style.display = 'none';
  } else {
    el.textContent = 'Not connected. Click "Connect Google Drive" to authorize.';
    actionsEl.style.display = '';
  }
}

// eslint-disable-next-line no-unused-vars
async function refreshDashboard() {
  const status = await API.getServiceStatus();

  if (status) {
    document.getElementById('status-grid').innerHTML =
      renderServiceCard('Telegram Bot', 'bot', status.bot) +
      renderServiceCard('Jenkins Agent', 'agent', status.agent);
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
