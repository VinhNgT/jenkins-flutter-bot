/* Tab navigation — show/hide panels, start/stop polling. */

import { refreshDriveCard } from './dashboard.js';

export function initTabs() {
  document.querySelectorAll('[data-tab]').forEach((btn) => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  // Keyboard navigation for sidebar
  const sidebar = document.querySelector('.sidebar');
  if (sidebar) {
    sidebar.addEventListener('keydown', (e) => {
      if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return;
      e.preventDefault();

      const buttons = [...sidebar.querySelectorAll('.sidebar-btn[data-tab]')];
      const focused = document.activeElement;
      const idx = buttons.indexOf(focused);
      if (idx === -1) return;

      let next;
      if (e.key === 'ArrowDown') {
        next = buttons[(idx + 1) % buttons.length];
      } else {
        next = buttons[(idx - 1 + buttons.length) % buttons.length];
      }
      next.focus();
      next.click();
    });
  }

  const saved = sessionStorage.getItem('activeTab') || 'dashboard';
  switchTab(saved);
}

export function switchTab(tabId) {
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

  if (tabId === 'file_manager') {
    refreshDriveCard();
  }

  sessionStorage.setItem('activeTab', tabId);
}
