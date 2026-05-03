/* === Config helpers === */

function nestedSet(target, dotted, value) {
  const parts = dotted.split('.');
  let current = target;
  for (const part of parts.slice(0, -1)) {
    if (!(part in current) || typeof current[part] !== 'object') {
      current[part] = {};
    }
    current = current[part];
  }
  current[parts[parts.length - 1]] = value;
}

function nestedGet(target, dotted) {
  return dotted.split('.').reduce((value, part) => {
    if (!value || typeof value !== 'object') return '';
    return value[part] ?? '';
  }, target);
}

function collectConfig() {
  const payload = { bot: {}, agent: {}, ui: {} };
  document.querySelectorAll('input[name], select[name]').forEach((el) => {
    const [scope, dotted] = el.name.split(':');
    nestedSet(payload[scope], dotted, el.value);
  });
  return payload;
}

function populateConfig(payload) {
  document.querySelectorAll('input[name], select[name]').forEach((el) => {
    const [scope, dotted] = el.name.split(':');
    el.value = nestedGet(payload[scope] || {}, dotted);
  });
}

/* === Log output === */

const logEl = document.getElementById('log');

function setLog(message) {
  logEl.textContent =
    typeof message === 'string' ? message : JSON.stringify(message, null, 2);
}

/* === Status rendering === */

function badgeClass(status) {
  if (status.available === false) return 'badge--unavailable';
  return status.running ? 'badge--running' : 'badge--stopped';
}

function badgeLabel(status) {
  if (status.available === false) return 'Unavailable';
  return status.running ? 'Running' : 'Stopped';
}

function renderStatusCard(name, key, status) {
  const cls = badgeClass(status);
  const label = badgeLabel(status);
  const details = [];
  if (status.configured !== undefined)
    details.push(`Configured: ${status.configured}`);
  if (status.drive_connected !== undefined)
    details.push(`Drive: ${status.drive_connected}`);
  if (status.pending_builds !== undefined)
    details.push(`Pending builds: ${status.pending_builds}`);
  const error = status.last_error ?? status.detail ?? null;
  if (error && error !== 'none') details.push(`Error: ${error}`);

  return `
    <div class="status-card">
      <div class="status-header">
        <h3>${name}</h3>
        <span class="badge ${cls}">${label}</span>
      </div>
      ${details.length ? `<div class="status-details">${details.map((d) => `<p>${d}</p>`).join('')}</div>` : ''}
      <div class="status-controls">
        <button class="btn-primary btn-sm" onclick="control('${key}','start')">Start</button>
        <button class="btn-secondary btn-sm" onclick="control('${key}','restart')">Restart</button>
        <button class="btn-danger btn-sm" onclick="control('${key}','stop')">Stop</button>
      </div>
    </div>
  `;
}

function renderDriveStatus(status) {
  if (!status.configured) {
    return `Bot Drive credentials are not configured yet. Token path: ${status.token_path}`;
  }
  const state = status.connected ? 'Connected' : 'Not connected';
  const pending = status.auth_pending
    ? ' Waiting for the Google callback.'
    : '';
  return `${state}. Token path: ${status.token_path}.${pending}`;
}

/* === API calls === */

async function refreshAll() {
  const [configRes, statusRes, driveRes] = await Promise.all([
    fetch('/api/config'),
    fetch('/api/services/status'),
    fetch('/api/drive/status'),
  ]);
  const config = await configRes.json();
  const status = await statusRes.json();
  const drive = await driveRes.json();

  populateConfig(config);

  document.getElementById('status-grid').innerHTML =
    renderStatusCard('Telegram Bot', 'bot', status.bot) +
    renderStatusCard('Jenkins Agent', 'agent', status.agent);

  document.getElementById('drive-status').textContent =
    renderDriveStatus(drive);

  setLog(status);
}

async function saveConfig() {
  const res = await fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(collectConfig()),
  });
  const result = await res.json();
  setLog(result);
  await refreshAll();
}

async function control(service, action) {
  const res = await fetch(`/api/services/${service}/${action}`, {
    method: 'POST',
  });
  const result = await res.json();
  setLog(result);
  await refreshAll();
}

async function startDriveSetup() {
  const res = await fetch('/api/drive/connect/start', { method: 'POST' });
  const result = await res.json();
  if (!res.ok) {
    setLog(result);
    return;
  }
  window.open(result.auth_url, '_blank', 'noopener');
  await refreshAll();
  setLog(
    'Google authorization opened in a new window. Finish approval there and the dashboard will update automatically.',
  );
}

/* === Collapsible sections === */

function initCollapsibles() {
  document.querySelectorAll('.collapsible-toggle').forEach((toggle) => {
    toggle.addEventListener('click', () => {
      const expanded = toggle.getAttribute('aria-expanded') === 'true';
      toggle.setAttribute('aria-expanded', String(!expanded));
    });
  });
}

/* === Event listeners === */

window.addEventListener('message', async (event) => {
  if (event.origin !== window.location.origin) return;
  if (event.data?.type !== 'drive-oauth-complete') return;
  await refreshAll();
  setLog(event.data.message);
});

document.getElementById('save-config').addEventListener('click', saveConfig);
document.getElementById('refresh-all').addEventListener('click', refreshAll);
document
  .getElementById('drive-start')
  .addEventListener('click', startDriveSetup);

initCollapsibles();
refreshAll().catch((error) => setLog(String(error)));
