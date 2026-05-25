/* Dynamic config form rendering from module schemas. */

import { Icons } from './icons.js';
import { toggleHelp } from './help.js';
import { Toast } from './toast.js';


const SCOPE_LABELS = { bot: 'Bot', agent: 'Agent', file_manager: 'File Manager', builds: 'Build Manager' };

/**
 * Render a config form panel from a module schema.
 * @param {string} containerId  - target div id (e.g. "schema-container-bot")
 * @param {string} scope        - "bot", "agent", "builds", or "file_manager"
 * @param {Object} schema       - { title, description, fields: [...] }
 */
export function renderSchemaForm(containerId, scope, schema) {
  const container = document.getElementById(containerId);
  if (!container || !schema) return;

  container.innerHTML = '';

  // Panel title + description
  const title = document.createElement('h2');
  title.className = 'panel-title';
  title.textContent = schema.title;
  container.appendChild(title);

  const desc = document.createElement('p');
  desc.className = 'panel-desc';
  desc.innerHTML = schema.description;
  container.appendChild(desc);

  // Group fields by their "group" property (preserve insertion order)
  const groups = new Map();
  for (const field of schema.fields) {
    if (!groups.has(field.group)) groups.set(field.group, []);
    groups.get(field.group).push(field);
  }

  // Render each group as a card
  for (const [groupName, fields] of groups) {
    const card = document.createElement('div');
    card.className = 'card';

    const h3 = document.createElement('h3');
    h3.textContent = groupName;
    card.appendChild(h3);

    const grid = document.createElement('div');
    grid.className = 'form-grid';
    grid.dataset.scope = scope;

    for (const field of fields) {
      grid.appendChild(_renderField(scope, field));
    }

    card.appendChild(grid);

    if (scope === 'agent' && groupName === 'VPN') {
      const vpnContainer = document.createElement('div');
      vpnContainer.className = 'vpn-upload-container';
      vpnContainer.style.marginTop = '1.5rem';
      vpnContainer.style.paddingTop = '1.5rem';
      vpnContainer.style.borderTop = '1px solid var(--border-color, #2d2d2d)';
      card.appendChild(vpnContainer);

      _initVpnWidget(vpnContainer);
    }

    container.appendChild(card);
  }

  // Save + Reload actions
  const label = SCOPE_LABELS[scope] || scope;
  const actions = document.createElement('div');
  actions.className = 'form-actions';
  actions.id = `form-actions-${scope}`;
  actions.innerHTML = `
    <button class="btn btn-accent" data-save="${scope}" type="button">${Icons.save}Save ${label} Config<span class="save-dot"></span></button>
    <button class="btn btn-secondary" data-reload="${scope}" type="button">${Icons.restart}Reload</button>
  `;
  container.appendChild(actions);

  // Track unsaved changes
  container.addEventListener('input', () => {
    const actionsEl = document.getElementById(`form-actions-${scope}`);
    if (actionsEl) actionsEl.classList.add('scope-dirty');
  });
  container.addEventListener('change', () => {
    const actionsEl = document.getElementById(`form-actions-${scope}`);
    if (actionsEl) actionsEl.classList.add('scope-dirty');
  });
}

/**
 * Render a single field element from a schema field definition.
 * @param {string} scope
 * @param {Object} f - field definition from schema
 * @returns {HTMLElement}
 */
function _renderField(scope, f) {
  const fieldDiv = document.createElement('div');
  fieldDiv.className = f.secret ? 'field field--secret' : 'field';
  if (f.secret) fieldDiv.dataset.secretKey = f.key;
  if (f.required) fieldDiv.dataset.required = '';

  // Label
  const label = document.createElement('label');
  label.textContent = f.label;
  if (f.required) {
    const marker = document.createElement('span');
    marker.className = 'required-marker';
    marker.textContent = ' *';
    label.appendChild(marker);
  }

  // Help button (only if help_html is provided)
  if (f.help_html) {
    const row = document.createElement('div');
    row.className = 'label-row';
    row.appendChild(label);

    const helpBtn = document.createElement('button');
    helpBtn.type = 'button';
    helpBtn.className = 'help-btn';
    helpBtn.setAttribute('aria-label', 'Show help');
    helpBtn.textContent = '?';
    helpBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleHelp(helpBtn, f.help_html);
    });
    row.appendChild(helpBtn);
    fieldDiv.appendChild(row);
  } else {
    fieldDiv.appendChild(label);
  }

  // Description
  if (f.description) {
    const desc = document.createElement('p');
    desc.className = 'field-desc';
    desc.textContent = f.description;
    fieldDiv.appendChild(desc);
  }

  // Input element
  const name = `${scope}:${f.key}`;
  if (f.secret) {
    const secretRow = document.createElement('div');
    secretRow.className = 'secret-row';

    const input = document.createElement('input');
    input.type = 'password';
    input.name = name;
    input.autocomplete = 'off';
    secretRow.appendChild(input);

    const changeBtn = document.createElement('button');
    changeBtn.type = 'button';
    changeBtn.className = 'btn btn-sm btn-secondary';
    changeBtn.dataset.action = 'change-secret';
    changeBtn.textContent = 'Change';
    secretRow.appendChild(changeBtn);

    const cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.className = 'btn btn-sm btn-secondary';
    cancelBtn.dataset.action = 'cancel-secret';
    cancelBtn.hidden = true;
    cancelBtn.textContent = 'Reset';
    secretRow.appendChild(cancelBtn);

    fieldDiv.appendChild(secretRow);
  } else if (f.field_type === 'select' && f.choices && f.choices.length) {
    const select = document.createElement('select');
    select.name = name;
    for (const [value, text] of f.choices) {
      const opt = document.createElement('option');
      opt.value = value;
      opt.textContent = text;
      select.appendChild(opt);
    }
    fieldDiv.appendChild(select);
  } else {
    const input = document.createElement('input');
    input.name = name;
    if (f.field_type === 'number') {
      input.type = 'number';
      input.min = '0';
    }
    if (f.default) {
      input.placeholder = f.default;
    }
    fieldDiv.appendChild(input);
  }

  return fieldDiv;
}

/**
 * Initialize OpenVPN configuration status widget.
 * @param {HTMLElement} container
 */
async function _initVpnWidget(container) {
  // Loading state first
  container.innerHTML = `
    <div class="vpn-status-loading" style="display:flex; align-items:center; gap: 0.5rem; color: var(--text-muted, #888); font-size: 0.9rem;">
      <span class="spinner" style="width:16px; height:16px; border:2px solid currentColor; border-top-color:transparent; border-radius:50%; animation:spin 1s linear infinite;"></span>
      Loading OpenVPN configuration status...
    </div>
  `;

  // Define the spin animation style dynamically if not already present
  if (!document.getElementById('spin-keyframes')) {
    const style = document.createElement('style');
    style.id = 'spin-keyframes';
    style.innerHTML = `
      @keyframes spin {
        to { transform: rotate(360deg); }
      }
    `;
    document.head.appendChild(style);
  }

  async function refreshStatus() {
    try {
      const res = await fetch('/api/services/agent/vpn/status');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      renderWidget(data);
    } catch (err) {
      container.innerHTML = `
        <div style="color: var(--color-error, #ff4d4d); font-size: 0.9rem;">
          Failed to load VPN status: ${err.message}
          <button class="btn btn-sm btn-secondary" style="margin-left: 0.5rem;" type="button" id="vpn-retry-btn">Retry</button>
        </div>
      `;
      const retryBtn = container.querySelector('#vpn-retry-btn');
      if (retryBtn) {
        retryBtn.addEventListener('click', () => refreshStatus());
      }
    }
  }

  function renderWidget(status) {
    container.innerHTML = '';

    const header = document.createElement('h4');
    header.style.margin = '0 0 0.75rem 0';
    header.style.fontSize = '0.95rem';
    header.style.fontWeight = '600';
    header.textContent = 'OpenVPN Config File (.ovpn)';
    container.appendChild(header);

    const statusRow = document.createElement('div');
    statusRow.style.display = 'flex';
    statusRow.style.alignItems = 'center';
    statusRow.style.justifyContent = 'space-between';
    statusRow.style.flexWrap = 'wrap';
    statusRow.style.gap = '1rem';
    statusRow.style.padding = '1rem';
    statusRow.style.borderRadius = '6px';
    statusRow.style.backgroundColor = 'var(--bg-card-sub, rgba(255,255,255,0.03))';
    statusRow.style.border = '1px solid var(--border-color, #2d2d2d)';

    if (status.uploaded) {
      // Configured UI
      const meta = document.createElement('div');
      meta.style.display = 'flex';
      meta.style.flexDirection = 'column';
      meta.style.gap = '0.25rem';
      
      const title = document.createElement('div');
      title.style.display = 'flex';
      title.style.alignItems = 'center';
      title.style.gap = '0.5rem';
      title.style.fontWeight = '500';
      title.style.color = 'var(--color-success, #2ec4b6)';
      title.innerHTML = `<span>✓</span> Configured`;

      const details = document.createElement('span');
      details.style.fontSize = '0.85rem';
      details.style.color = 'var(--text-muted, #888)';
      const sizeKB = (status.size / 1024).toFixed(2);
      details.textContent = `.ovpn file uploaded (${sizeKB} KB)`;
      
      meta.appendChild(title);
      meta.appendChild(details);

      // Connection status, if connected
      if (status.connected) {
        const activeBadge = document.createElement('span');
        activeBadge.style.fontSize = '0.75rem';
        activeBadge.style.padding = '0.15rem 0.4rem';
        activeBadge.style.borderRadius = '4px';
        activeBadge.style.backgroundColor = 'rgba(46, 196, 182, 0.15)';
        activeBadge.style.color = 'var(--color-success, #2ec4b6)';
        activeBadge.style.border = '1px solid rgba(46, 196, 182, 0.3)';
        activeBadge.style.fontWeight = '600';
        activeBadge.textContent = 'Active Build Connection';
        title.appendChild(activeBadge);
      }

      statusRow.appendChild(meta);

      const removeBtn = document.createElement('button');
      removeBtn.className = 'btn btn-sm btn-secondary';
      removeBtn.style.borderColor = 'rgba(255, 77, 77, 0.3)';
      removeBtn.style.color = '#ff4d4d';
      removeBtn.type = 'button';
      removeBtn.textContent = 'Remove config';
      removeBtn.addEventListener('click', async () => {
        if (!confirm('Are you sure you want to delete the uploaded OpenVPN configuration file? This will stop VPN builds.')) return;
        removeBtn.disabled = true;
        removeBtn.textContent = 'Removing...';
        try {
          const res = await fetch('/api/services/agent/vpn/upload', { method: 'DELETE' });
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          Toast.show('OpenVPN configuration file removed', 'info');
          refreshStatus();
        } catch (err) {
          Toast.show(`Failed to delete config: ${err.message}`, 'error');
          removeBtn.disabled = false;
          removeBtn.textContent = 'Remove config';
        }
      });
      statusRow.appendChild(removeBtn);
    } else {
      // Not configured UI
      const meta = document.createElement('div');
      meta.style.display = 'flex';
      meta.style.flexDirection = 'column';
      meta.style.gap = '0.25rem';
      
      const title = document.createElement('div');
      title.style.fontWeight = '500';
      title.style.color = 'var(--text-muted, #888)';
      title.textContent = 'No configuration uploaded';

      const details = document.createElement('span');
      details.style.fontSize = '0.85rem';
      details.style.color = 'var(--text-muted, #666)';
      details.textContent = 'Upload a .ovpn file to enable private network builds.';

      meta.appendChild(title);
      meta.appendChild(details);
      statusRow.appendChild(meta);

      const fileLabel = document.createElement('label');
      fileLabel.className = 'btn btn-sm btn-secondary';
      fileLabel.style.cursor = 'pointer';
      fileLabel.style.margin = '0';
      fileLabel.innerHTML = `
        Choose file...
        <input type="file" accept=".ovpn" style="display: none;" />
      `;
      
      const fileInput = fileLabel.querySelector('input');
      fileInput.addEventListener('change', async () => {
        if (!fileInput.files.length) return;
        const file = fileInput.files[0];
        if (!file.name.endsWith('.ovpn')) {
          Toast.show('Please upload a valid .ovpn file', 'error');
          return;
        }

        fileLabel.style.opacity = '0.6';
        fileLabel.style.pointerEvents = 'none';
        fileLabel.innerHTML = `Uploading... <input type="file" accept=".ovpn" style="display: none;" />`;

        const formData = new FormData();
        formData.append('file', file);

        try {
          const res = await fetch('/api/services/agent/vpn/upload', {
            method: 'POST',
            body: formData
          });
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          Toast.show('OpenVPN configuration file uploaded successfully', 'success');
          refreshStatus();
        } catch (err) {
          Toast.show(`Failed to upload config: ${err.message}`, 'error');
          refreshStatus();
        }
      });

      statusRow.appendChild(fileLabel);
    }

    container.appendChild(statusRow);
  }

  // Initial load
  await refreshStatus();
}

