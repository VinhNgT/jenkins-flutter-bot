/* Tab navigation — show/hide panels, start/stop polling. */

// eslint-disable-next-line no-unused-vars
function initTabs() {
  document.querySelectorAll('[data-tab]').forEach((btn) => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });
  const saved = sessionStorage.getItem('activeTab') || 'dashboard';
  switchTab(saved);
}

// eslint-disable-next-line no-unused-vars
function switchTab(tabId) {
  document.querySelectorAll('.sidebar-btn[data-tab]').forEach((btn) => {
    const isActive = btn.dataset.tab === tabId;
    btn.classList.toggle('active', isActive);
    btn.setAttribute('aria-selected', String(isActive));
  });

  document.querySelectorAll('.tab-panel').forEach((panel) => {
    const isActive = panel.id === `panel-${tabId}`;
    panel.classList.toggle('active', isActive);
    panel.hidden = !isActive;
  });

  Poller.stop();
  if (tabId === 'dashboard') {
    Poller.start(refreshDashboard);
  }

  sessionStorage.setItem('activeTab', tabId);
}
