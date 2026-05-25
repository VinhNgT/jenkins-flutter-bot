/* Entry point — initialize all modules and wire event listeners. */

import { Toast } from './toast.js';
import { API } from './api.js';
import { renderSchemaForm } from './schema-renderer.js';
import { collectScope, populateScope, validateScope, initSecretFields } from './config.js';
import { initHelpPopovers } from './help.js';
import { Poller, refreshDashboard, refreshDriveCard, controlService, handleStop } from './dashboard.js';
import { initTabs, switchTab } from './tabs.js';
import { Icons } from './icons.js';

// Expose to inline onclick handlers in dynamically generated HTML
window.controlService = controlService;
window.handleStop = handleStop;
window.switchTab = switchTab;

async function loadVersion() {
  try {
    const res = await fetch('/api/version');
    if (!res.ok) return;
    const { version } = await res.json();
    const el = document.getElementById('version-badge');
    if (el && version) {
      el.textContent = 'v' + version;
      el.classList.add('loaded');
    }
  } catch {
    // silently ignore — the badge stays empty
  }
}

function loadGithubLink(schemas, config) {
  // Resolve github_url: saved config value first, then schema default.
  const configUrl = config?.bot?.project?.github_url ?? '';
  const schemaDefault = schemas?.bot?.fields
    ?.find(f => f.key === 'project.github_url')?.default ?? '';
  const url = (configUrl || schemaDefault).trim();

  const ghLink = document.getElementById('github-link');
  if (ghLink && url) {
    ghLink.href = url;
    ghLink.removeAttribute('hidden');
  }
}

document.addEventListener('DOMContentLoaded', async () => {
  // Initialize global modules
  initSecretFields();
  initHelpPopovers();
  loadVersion();

  // ─── Schema-first rendering ───────────────────────────────────
  // Fetch schemas from all modules, render forms, then populate values.
  const [schemas, config] = await Promise.all([
    API.getSchema(),
    API.getConfig(),
  ]);

  // Render dynamic forms from schemas
  if (schemas) {
    if (schemas.bot) renderSchemaForm('schema-container-bot', 'bot', schemas.bot);
    if (schemas.builds) renderSchemaForm('schema-container-builds', 'builds', schemas.builds);
    if (schemas.agent) renderSchemaForm('schema-container-agent', 'agent', schemas.agent);
    if (schemas.file_manager) renderSchemaForm('schema-container-file_manager', 'file_manager', schemas.file_manager);
  }

  // Populate the GitHub header link from schema + config
  loadGithubLink(schemas, config);

  // Populate values into rendered forms
  if (config) {
    populateScope('bot', config.bot, config._secrets_set?.bot);
    populateScope('builds', config.builds, config._secrets_set?.builds);
    populateScope('agent', config.agent, config._secrets_set?.agent);
    populateScope('file_manager', config.file_manager, config._secrets_set?.file_manager);
  }

  // Show error state if both schema and config fail
  if (!schemas && !config) {
    const content = document.querySelector('.content');
    if (content) {
      content.innerHTML = `
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:50vh;text-align:center;">
          <h2 class="panel-title">Unable to Load Dashboard</h2>
          <p class="panel-desc">Could not connect to the config-hub API. Check that all services are running.</p>
          <button class="btn btn-accent" onclick="location.reload()">Retry</button>
        </div>`;
      return;
    }
  }

  // ─── Delegated save/reload handlers ───────────────────────────
  // Uses event delegation on dynamic buttons created by schema-renderer.js
  document.addEventListener('click', async (e) => {
    // Save buttons: data-save="bot|agent|ui"
    const saveBtn = e.target.closest('[data-save]');
    if (saveBtn) {
      const scope = saveBtn.dataset.save;
      const { valid, missing } = validateScope(scope);
      if (!valid) {
        Toast.show(`Missing required fields: ${missing.join(', ')}`, 'error');
        return;
      }
      const data = collectScope(scope);
      const result = await API.saveScope(scope, data);
      if (result) {
        const label = { bot: 'Bot', builds: 'Build Manager', agent: 'Agent', file_manager: 'File Manager' }[scope] || scope;
        
        // Upload pending VPN file if there is one
        if (scope === 'agent' && window.pendingVpnFile) {
          const formData = new FormData();
          formData.append('file', window.pendingVpnFile);
          try {
            const uploadRes = await fetch('/api/services/agent/vpn/upload', {
              method: 'POST',
              body: formData
            });
            if (!uploadRes.ok) throw new Error(`HTTP ${uploadRes.status}`);
            window.pendingVpnFile = null;
            Toast.show(`${label} config and OpenVPN profile saved successfully`, 'success');
          } catch (err) {
            Toast.show(`Config saved but failed to upload OpenVPN file: ${err.message}`, 'error');
          }
        } else {
          Toast.show(`${label} config saved`, 'success');
        }

        // Clear unsaved indicator
        const actionsEl = document.getElementById(`form-actions-${scope}`);
        if (actionsEl) actionsEl.classList.remove('scope-dirty');
        const freshConfig = await API.getConfig();
        if (freshConfig) populateScope(scope, freshConfig[scope], freshConfig._secrets_set?.[scope]);
        if (scope === 'file_manager') await refreshDriveCard();
        if (scope === 'agent' && window.refreshVpnWidgetStatus) {
          await window.refreshVpnWidgetStatus();
        }
      }
      return;
    }

    // Reload buttons: data-reload="bot|agent|builds|file_manager"
    const reloadBtn = e.target.closest('[data-reload]');
    if (reloadBtn) {
      const scope = reloadBtn.dataset.reload;
      if (scope === 'agent') {
        window.pendingVpnFile = null;
      }
      const freshConfig = await API.getConfig();
      if (freshConfig) populateScope(scope, freshConfig[scope], freshConfig._secrets_set?.[scope]);
      if (scope === 'file_manager') await refreshDriveCard();
      if (scope === 'agent' && window.refreshVpnWidgetStatus) {
        await window.refreshVpnWidgetStatus();
      }
      // Clear unsaved indicator
      const actionsEl = document.getElementById(`form-actions-${scope}`);
      if (actionsEl) actionsEl.classList.remove('scope-dirty');
      const label = { bot: 'Bot', builds: 'Build Manager', agent: 'Agent', file_manager: 'File Manager' }[scope] || scope;
      Toast.show(`${label} config reloaded`, 'info');
      return;
    }
  });

  // ─── OAuth dialog ─────────────────────────────────────────────
  const oauthDialog = document.getElementById('oauth-dialog');
  const oauthCancelBtn = document.getElementById('oauth-cancel-btn');
  const driveToggleBtn = document.getElementById('drive-connect-toggle');

  // Prevent Escape from closing the dialog (would leave Google tab orphaned)
  oauthDialog.addEventListener('cancel', (e) => e.preventDefault());

  // Shared OAuth popup flow — called by both Connect and Change Account
  async function startOAuthFlow(triggerBtn) {
    triggerBtn.disabled = true;

    const result = await API.startDriveConnect();
    if (!result?.auth_url) {
      triggerBtn.disabled = false;
      return;
    }

    // Show modal BEFORE opening Google tab so user sees it first
    oauthDialog.showModal();

    // No 'noopener' — we need window.opener for postMessage callback
    // and the reference for popup.closed polling
    const popup = window.open(result.auth_url, '_blank');
    triggerBtn.disabled = false;

    // Handle popup blocked by browser
    if (!popup) {
      oauthDialog.close();
      Toast.show('Popup was blocked. Please allow popups for this site.', 'error');
      return;
    }

    let oauthCompleted = false;

    // Cancel button closes the Google tab → poller detects it → closes dialog
    oauthCancelBtn.onclick = () => popup.close();

    // Track completion via custom event (set by message listener below)
    const onComplete = () => { oauthCompleted = true; };
    window.addEventListener('drive-oauth-done', onComplete, { once: true });

    // Poll for Google tab close — reset UI if user abandoned the flow
    const poll = setInterval(() => {
      if (popup.closed) {
        clearInterval(poll);
        window.removeEventListener('drive-oauth-done', onComplete);
        if (!oauthCompleted) {
          oauthDialog.close();
          refreshDriveCard();
        }
      }
    }, 500);
  }

  // Toggle button — "Connect Google Drive" when disconnected, "Change Account" when connected
  driveToggleBtn.addEventListener('click', () => startOAuthFlow(driveToggleBtn));

  // Disconnect — deletes the token file without re-authorizing
  const driveDisconnectBtn = document.getElementById('drive-disconnect');
  driveDisconnectBtn.addEventListener('click', async () => {
    driveDisconnectBtn.disabled = true;
    const result = await API.disconnectDrive();
    driveDisconnectBtn.disabled = false;
    if (result) {
      Toast.show('Google Drive disconnected', 'info');
      await refreshDriveCard();
    }
  });

  // Drive OAuth callback via postMessage from oauth_callback.html
  window.addEventListener('message', async (event) => {
    if (event.origin !== window.location.origin) return;
    if (event.data?.type !== 'drive-oauth-complete') return;
    // Signal completion FIRST so poller sees oauthCompleted = true
    window.dispatchEvent(new Event('drive-oauth-done'));
    oauthDialog.close();
    const type = event.data.success ? 'success' : 'error';
    Toast.show(event.data.message, type);
    await refreshDriveCard();
  });

  // ─── Jenkinsfile generator ──────────────────────────────────────
  const jfPublicNotices     = document.getElementById('jf-public-notices');
  const jfPrivateNotices    = document.getElementById('jf-private-notices');
  const jenkinsfileTabs     = document.getElementById('jenkinsfile-tabs');
  const jfPanelPublic       = document.getElementById('jf-panel-public');
  const jfPanelPrivate      = document.getElementById('jf-panel-private');
  const jfOutputPublic      = document.getElementById('jenkinsfile-output-public');
  const jfOutputPrivate     = document.getElementById('jenkinsfile-output-private');
  const jfCopyPublic        = document.getElementById('jenkinsfile-copy-public');
  const jfCopyPrivate       = document.getElementById('jenkinsfile-copy-private');
  const jfParamRepoUrl      = document.getElementById('jf-param-repo-url');
  const jfParamCredentialsId = document.getElementById('jf-param-credentials-id');

  // Load saved repository params from localStorage
  if (jfParamRepoUrl) {
    jfParamRepoUrl.value = localStorage.getItem('jf_repo_url') || '';
    jfParamRepoUrl.addEventListener('input', () => {
      localStorage.setItem('jf_repo_url', jfParamRepoUrl.value.trim());
    });
  }
  if (jfParamCredentialsId) {
    jfParamCredentialsId.value = localStorage.getItem('jf_credentials_id') || '';
    jfParamCredentialsId.addEventListener('input', () => {
      localStorage.setItem('jf_credentials_id', jfParamCredentialsId.value.trim());
    });
  }

  let activeJfTab = 'public';

  function switchJfTab(tab) {
    activeJfTab = tab;
    jfPanelPublic.hidden  = (tab !== 'public');
    jfPanelPrivate.hidden = (tab !== 'private');
    jenkinsfileTabs.querySelectorAll('[data-jf-tab]').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.jfTab === tab);
    });
  }

  jenkinsfileTabs.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-jf-tab]');
    if (btn) switchJfTab(btn.dataset.jfTab);
  });

  document.getElementById('jenkinsfile-generate').addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    jfOutputPublic.value  = 'Generating…';
    jfOutputPrivate.value = 'Generating…';

    const discard_builds = document.getElementById('opt-discard-builds').checked;
    const clean_workspace = document.getElementById('opt-clean-workspace').checked;
    const shallow_clone = document.getElementById('opt-shallow-clone').checked;
    const repo_url = jfParamRepoUrl ? jfParamRepoUrl.value.trim() : '';
    const credentials_id = jfParamCredentialsId ? jfParamCredentialsId.value.trim() : '';

    const result = await API.getJenkinsfile({
      discard_builds,
      clean_workspace,
      shallow_clone,
      repo_url,
      credentials_id,
    });
    btn.disabled = false;

    if (!result) {
      jfOutputPublic.value  = '';
      jfOutputPrivate.value = '';
      return;
    }

    jfOutputPublic.value  = result.script_public  ?? '';
    jfOutputPrivate.value = result.script_private ?? '';
    jfCopyPublic.disabled  = false;
    jfCopyPrivate.disabled = false;
    jenkinsfileTabs.hidden = false;
    switchJfTab(activeJfTab);

    // Clear previous notices
    jfPublicNotices.innerHTML = '';
    jfPrivateNotices.innerHTML = '';

    if (result.warnings?.length) {
      result.warnings.forEach(w => {
        if (w.includes("Repository URL")) {
          // Repo URL warning applies to both public and private repos
          const createNotice = () => {
            const div = document.createElement('div');
            div.className = 'jf-placeholder-notice';
            div.innerHTML = `<span class="notice-icon">ℹ️</span><span>Using placeholder <code>&lt;YOUR_REPO_URL&gt;</code>. Configure your Git URL in the <strong>Repository Settings</strong> above for a ready-to-copy script.</span>`;
            return div;
          };
          jfPublicNotices.appendChild(createNotice());
          jfPrivateNotices.appendChild(createNotice());
        } else if (w.includes("Repo Credentials ID")) {
          // Credentials warning ONLY applies to private repos
          const div = document.createElement('div');
          div.className = 'jf-placeholder-notice';
          div.innerHTML = `<span class="notice-icon">ℹ️</span><span>Using placeholder <code>&lt;YOUR_CREDENTIALS_ID&gt;</code>. Configure your Credentials ID in the <strong>Repository Settings</strong> above or replace it in the script.</span>`;
          jfPrivateNotices.appendChild(div);
        }
      });
    }

    Toast.show('Jenkinsfiles generated', 'success');
  });

  async function copyToClipboard(text) {
    try {
      await navigator.clipboard.writeText(text);
      Toast.show('Copied to clipboard', 'success');
    } catch {
      Toast.show('Press Ctrl+C to copy', 'info');
    }
  }

  jfCopyPublic.addEventListener('click',  () => copyToClipboard(jfOutputPublic.value));
  jfCopyPrivate.addEventListener('click', () => copyToClipboard(jfOutputPrivate.value));


  // ─── Config Transfer (export + import) ──────────────────────────
  const exportOutput = document.getElementById('export-output');
  const exportWarnings = document.getElementById('export-warnings');
  const exportCopyBtn = document.getElementById('export-copy');
  const exportDownloadBtn = document.getElementById('export-download');
  const exportTabs = document.getElementById('export-tabs');

  // Cached export data from the last generate
  let exportData = null;
  let activeExportTab = 'bot';

  function getTabContent(tab) {
    if (!exportData) return '';
    if (tab === 'bot') return exportData.files['bot.env'] || '';
    if (tab === 'agent') return exportData.files['agent.env'] || '';
    if (tab === 'file_manager') return exportData.files['file_manager.env'] || '';
    if (tab === 'compose') {
      const bot = exportData.compose_vars?.bot || '';
      const agent = exportData.compose_vars?.agent || '';
      return bot + '\n' + agent;
    }
    return '';
  }

  function switchExportTab(tab) {
    activeExportTab = tab;
    exportOutput.value = getTabContent(tab);
    exportTabs.querySelectorAll('.export-tab').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.exportTab === tab);
    });
  }

  // Tab clicks
  exportTabs.addEventListener('click', (e) => {
    const tab = e.target.closest('[data-export-tab]');
    if (tab) switchExportTab(tab.dataset.exportTab);
  });

  document.getElementById('export-generate').addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    exportOutput.value = 'Generating…';

    const result = await API.getExportEnv();
    btn.disabled = false;

    if (!result) {
      exportOutput.value = '';
      return;
    }

    exportData = result;
    exportTabs.hidden = false;
    switchExportTab('bot');
    exportCopyBtn.disabled = false;
    exportDownloadBtn.disabled = false;

    if (result.warnings?.length) {
      exportWarnings.innerHTML = result.warnings
        .map(w => `<p>⚠️ ${w}</p>`)
        .join('');
      exportWarnings.hidden = false;
    } else {
      exportWarnings.hidden = true;
    }

    Toast.show('Config preview generated', 'success');
  });

  exportCopyBtn.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(exportOutput.value);
      Toast.show('Copied to clipboard', 'success');
    } catch {
      exportOutput.select();
      Toast.show('Press Ctrl+C to copy', 'info');
    }
  });

  exportDownloadBtn.addEventListener('click', async () => {
    exportDownloadBtn.disabled = true;
    const ok = await API.downloadTarball();
    exportDownloadBtn.disabled = false;
    if (ok) Toast.show('Tarball downloaded', 'success');
  });

  // ─── Import ────────────────────────────────────────────────────
  const importZone = document.getElementById('import-zone');
  const importFile = document.getElementById('import-file');
  const importBrowse = document.getElementById('import-browse');
  const importFilename = document.getElementById('import-filename');
  const importUploadBtn = document.getElementById('import-upload');
  const importResults = document.getElementById('import-results');

  let selectedFile = null;

  importBrowse.addEventListener('click', (e) => {
    e.preventDefault();
    importFile.click();
  });

  importFile.addEventListener('change', () => {
    if (importFile.files.length) {
      selectedFile = importFile.files[0];
      importFilename.textContent = selectedFile.name;
      importUploadBtn.disabled = false;
    }
  });

  // Drag and drop
  importZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    importZone.classList.add('dragover');
  });
  importZone.addEventListener('dragleave', () => {
    importZone.classList.remove('dragover');
  });
  importZone.addEventListener('drop', (e) => {
    e.preventDefault();
    importZone.classList.remove('dragover');
    if (e.dataTransfer.files.length) {
      selectedFile = e.dataTransfer.files[0];
      importFilename.textContent = selectedFile.name;
      importUploadBtn.disabled = false;
    }
  });

  importUploadBtn.addEventListener('click', async () => {
    if (!selectedFile) return;
    importUploadBtn.disabled = true;

    const result = await API.importTarball(selectedFile);
    importUploadBtn.disabled = false;

    if (!result) return;

    // Show results
    const sections = [];
    if (result.applied?.length) {
      sections.push(`<h4>✅ Applied (${result.applied.length})</h4><ul>${result.applied.map(s => `<li>${s}</li>`).join('')}</ul>`);
    }
    if (result.skipped_empty?.length) {
      sections.push(`<h4>⏭️ Skipped (${result.skipped_empty.length})</h4><ul>${result.skipped_empty.map(s => `<li>${s}</li>`).join('')}</ul>`);
    }
    if (result.unrecognized?.length) {
      sections.push(`<h4>❓ Unrecognized (${result.unrecognized.length})</h4><ul>${result.unrecognized.map(s => `<li>${s}</li>`).join('')}</ul>`);
    }
    if (result.parse_errors?.length) {
      sections.push(`<h4>❌ Errors (${result.parse_errors.length})</h4><ul>${result.parse_errors.map(s => `<li>${s}</li>`).join('')}</ul>`);
    }
    if (result.warnings?.length) {
      sections.push(`<h4>⚠️ Warnings (${result.warnings.length})</h4><ul>${result.warnings.map(s => `<li>${s}</li>`).join('')}</ul>`);
    }

    importResults.innerHTML = sections.join('') || '<p>No changes applied.</p>';
    importResults.hidden = false;

    const applied = result.applied?.length || 0;
    Toast.show(`Import complete — ${applied} field(s) applied`, applied ? 'success' : 'info');

    // Reset file input
    selectedFile = null;
    importFile.value = '';
    importFilename.textContent = '';
  });

  // Start the global service status real-time stream
  Poller.start(refreshDashboard);

  // Initialize tabs last (starts polling if on dashboard)
  initTabs();
});
