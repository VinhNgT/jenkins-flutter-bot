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

  // Drive connect button
  document.getElementById('drive-connect').addEventListener('click', async () => {
    const result = await API.startDriveConnect();
    if (result && result.auth_url) {
      window.open(result.auth_url, '_blank', 'noopener');
      Toast.show('Google authorization opened in new window', 'info');
    }
  });

  // Drive OAuth callback via postMessage
  window.addEventListener('message', async (event) => {
    if (event.origin !== window.location.origin) return;
    if (event.data?.type !== 'drive-oauth-complete') return;
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
