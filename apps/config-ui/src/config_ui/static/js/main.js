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

  // Initialize tabs last (starts polling if on dashboard)
  initTabs();
});
