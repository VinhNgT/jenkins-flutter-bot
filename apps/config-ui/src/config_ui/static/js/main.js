/* Entry point — initialize all modules and wire event listeners. */

document.addEventListener('DOMContentLoaded', async () => {
  // Initialize modules
  initSecretFields();
  initHelpButtons();

  // Per-tab save buttons
  document.getElementById('save-bot').addEventListener('click', async () => {
    const { valid, missing } = validateScope('bot');
    if (!valid) {
      Toast.show(`Missing required fields: ${missing.join(', ')}`, 'error');
      return;
    }
    const data = collectScope('bot');
    const result = await API.saveScope('bot', data);
    if (result) {
      Toast.show('Bot config saved', 'success');
      const config = await API.getConfig();
      if (config) populateScope('bot', config.bot, config._secrets_set?.bot);
    }
  });

  document.getElementById('save-agent').addEventListener('click', async () => {
    const { valid, missing } = validateScope('agent');
    if (!valid) {
      Toast.show(`Missing required fields: ${missing.join(', ')}`, 'error');
      return;
    }
    const data = collectScope('agent');
    const result = await API.saveScope('agent', data);
    if (result) {
      Toast.show('Agent config saved', 'success');
      const config = await API.getConfig();
      if (config) populateScope('agent', config.agent, config._secrets_set?.agent);
    }
  });

  document.getElementById('save-ui').addEventListener('click', async () => {
    const { valid, missing } = validateScope('ui');
    if (!valid) {
      Toast.show(`Missing required fields: ${missing.join(', ')}`, 'error');
      return;
    }
    const data = collectScope('ui');
    const result = await API.saveScope('ui', data);
    if (result) {
      Toast.show('Drive config saved', 'success');
      const config = await API.getConfig();
      if (config) populateScope('ui', config.ui, config._secrets_set?.ui);
      await refreshDriveTab();
    }
  });

  // Reload buttons
  document.getElementById('reload-bot').addEventListener('click', async () => {
    const config = await API.getConfig();
    if (config) populateScope('bot', config.bot, config._secrets_set?.bot);
    Toast.show('Bot config reloaded', 'info');
  });

  document.getElementById('reload-agent').addEventListener('click', async () => {
    const config = await API.getConfig();
    if (config) populateScope('agent', config.agent, config._secrets_set?.agent);
    Toast.show('Agent config reloaded', 'info');
  });

  document.getElementById('reload-drive').addEventListener('click', async () => {
    const config = await API.getConfig();
    if (config) populateScope('ui', config.ui, config._secrets_set?.ui);
    await refreshDriveTab();
    Toast.show('Drive config reloaded', 'info');
  });

  // OAuth dialog elements
  const oauthDialog = document.getElementById('oauth-dialog');
  const oauthCancelBtn = document.getElementById('oauth-cancel-btn');
  const driveConnectBtn = document.getElementById('drive-connect');

  // Prevent Escape from closing the dialog (would leave Google tab orphaned)
  oauthDialog.addEventListener('cancel', (e) => e.preventDefault());

  // Drive connect button
  driveConnectBtn.addEventListener('click', async () => {
    driveConnectBtn.disabled = true;

    const result = await API.startDriveConnect();
    if (!result?.auth_url) {
      driveConnectBtn.disabled = false;
      return;
    }

    // Show modal BEFORE opening Google tab so user sees it first
    oauthDialog.showModal();

    // No 'noopener' — we need window.opener for postMessage callback
    // and the reference for popup.closed polling
    const popup = window.open(result.auth_url, '_blank');
    driveConnectBtn.disabled = false;

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
    window.addEventListener('_driveOAuthDone', onComplete, { once: true });

    // Poll for Google tab close — reset UI if user abandoned the flow
    const poll = setInterval(() => {
      if (popup.closed) {
        clearInterval(poll);
        window.removeEventListener('_driveOAuthDone', onComplete);
        if (!oauthCompleted) {
          oauthDialog.close();
          refreshDriveTab();
        }
      }
    }, 500);
  });

  // Drive OAuth callback via postMessage from oauth_callback.html
  window.addEventListener('message', async (event) => {
    if (event.origin !== window.location.origin) return;
    if (event.data?.type !== 'drive-oauth-complete') return;
    // Signal completion FIRST so poller sees oauthCompleted = true
    window.dispatchEvent(new Event('_driveOAuthDone'));
    oauthDialog.close();
    const type = event.data.success ? 'success' : 'error';
    Toast.show(event.data.message, type);
    await refreshDriveTab();
    // Also refresh dashboard if it's active
    if (sessionStorage.getItem('activeTab') === 'dashboard') {
      await refreshDashboard();
    }
  });

  // Load initial config
  const config = await API.getConfig();
  if (config) populateAll(config);

  // Initialize tabs last (starts polling if on dashboard)
  initTabs();
});
