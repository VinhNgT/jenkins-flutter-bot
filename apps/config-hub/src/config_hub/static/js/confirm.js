/* Reusable confirmation modal — styled <dialog> element. */

/**
 * Show a confirmation dialog and return a Promise.
 * @param {Object} opts
 * @param {string} opts.title       - Dialog title
 * @param {string} opts.message     - Body message
 * @param {string} [opts.confirmLabel='Confirm'] - Confirm button text
 * @param {string} [opts.cancelLabel='Cancel']   - Cancel button text
 * @param {boolean} [opts.danger=false] - If true, confirm button uses danger style
 * @returns {Promise<boolean>} true if confirmed, false if cancelled
 */
export function showConfirm({ title, message, confirmLabel = 'Confirm', cancelLabel = 'Cancel', danger = false }) {
  return new Promise((resolve) => {
    const dialog = document.getElementById('confirm-dialog');
    if (!dialog) { resolve(false); return; }

    dialog.querySelector('.confirm-dialog-title').textContent = title;
    dialog.querySelector('.confirm-dialog-msg').textContent = message;

    const confirmBtn = dialog.querySelector('[data-action="confirm"]');
    const cancelBtn = dialog.querySelector('[data-action="cancel"]');

    confirmBtn.textContent = confirmLabel;
    cancelBtn.textContent = cancelLabel;
    confirmBtn.className = danger ? 'btn btn-danger' : 'btn btn-accent';

    function cleanup() {
      confirmBtn.removeEventListener('click', onConfirm);
      cancelBtn.removeEventListener('click', onCancel);
      dialog.removeEventListener('cancel', onCancel);
      dialog.close();
    }

    function onConfirm() { cleanup(); resolve(true); }
    function onCancel()  { cleanup(); resolve(false); }

    confirmBtn.addEventListener('click', onConfirm);
    cancelBtn.addEventListener('click', onCancel);
    dialog.addEventListener('cancel', onCancel); // ESC key

    dialog.showModal();
  });
}
