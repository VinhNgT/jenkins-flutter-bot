/* Toast notification system. */

// eslint-disable-next-line no-unused-vars
const Toast = {
  /**
   * Show a toast notification.
   * @param {string} message
   * @param {'success'|'error'|'info'} type
   */
  show(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const el = document.createElement('div');
    el.className = `toast toast--${type}`;
    el.textContent = message;
    container.appendChild(el);

    // Trigger enter transition
    requestAnimationFrame(() => el.classList.add('visible'));

    // Auto-dismiss
    setTimeout(() => {
      el.classList.remove('visible');
      setTimeout(() => el.remove(), 200);
    }, 4000);
  },
};
