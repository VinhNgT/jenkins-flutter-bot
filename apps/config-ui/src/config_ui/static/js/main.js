/* Entry point — initialize all modules and wire event listeners. */

document.addEventListener('DOMContentLoaded', async () => {
  // Initialize global modules
  initSecretFields();
  initHelpPopovers();

  // ─── Schema-first rendering ───────────────────────────────────
  // Fetch schemas from all modules, render forms, then populate values.
  const [schemas, config] = await Promise.all([
    API.getSchema(),
    API.getConfig(),
  ]);

  // Render dynamic forms from schemas
  if (schemas) {
    if (schemas.bot) renderSchemaForm('schema-container-bot', 'bot', schemas.bot);
    if (schemas.agent) renderSchemaForm('schema-container-agent', 'agent', schemas.agent);
    if (schemas.ui) renderSchemaForm('schema-container-ui', 'ui', schemas.ui);
  }

  // Populate values into rendered forms
  if (config) {
    populateScope('bot', config.bot, config._secrets_set?.bot);
    populateScope('agent', config.agent, config._secrets_set?.agent);
    populateScope('ui', config.ui, config._secrets_set?.ui);
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
        const label = { bot: 'Bot', agent: 'Agent', ui: 'Drive' }[scope] || scope;
        Toast.show(`${label} config saved`, 'success');
        const freshConfig = await API.getConfig();
        if (freshConfig) populateScope(scope, freshConfig[scope], freshConfig._secrets_set?.[scope]);
        if (scope === 'ui') await refreshDriveCard();
      }
      return;
    }

    // Reload buttons: data-reload="bot|agent|ui"
    const reloadBtn = e.target.closest('[data-reload]');
    if (reloadBtn) {
      const scope = reloadBtn.dataset.reload;
      const freshConfig = await API.getConfig();
      if (freshConfig) populateScope(scope, freshConfig[scope], freshConfig._secrets_set?.[scope]);
      if (scope === 'ui') await refreshDriveCard();
      const label = { bot: 'Bot', agent: 'Agent', ui: 'Drive' }[scope] || scope;
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
  const jenkinsfileOutput = document.getElementById('jenkinsfile-output');
  const jenkinsfileWarnings = document.getElementById('jenkinsfile-warnings');
  const jenkinsfileCopyBtn = document.getElementById('jenkinsfile-copy');

  document.getElementById('jenkinsfile-generate').addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    jenkinsfileOutput.value = 'Generating…';

    const result = await API.getJenkinsfile();
    btn.disabled = false;

    if (!result) {
      jenkinsfileOutput.value = '';
      return;
    }

    jenkinsfileOutput.value = result.script;
    jenkinsfileCopyBtn.disabled = false;

    // Show warnings if any
    if (result.warnings?.length) {
      jenkinsfileWarnings.innerHTML = result.warnings
        .map(w => `<p>⚠️ ${w}</p>`)
        .join('');
      jenkinsfileWarnings.hidden = false;
    } else {
      jenkinsfileWarnings.hidden = true;
    }

    Toast.show('Jenkinsfile generated', 'success');
  });

  jenkinsfileCopyBtn.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(jenkinsfileOutput.value);
      Toast.show('Copied to clipboard', 'success');
    } catch {
      // Fallback: select all text for manual copy
      jenkinsfileOutput.select();
      Toast.show('Press Ctrl+C to copy', 'info');
    }
  });

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

  // Initialize tabs last (starts polling if on dashboard)
  initTabs();
});
