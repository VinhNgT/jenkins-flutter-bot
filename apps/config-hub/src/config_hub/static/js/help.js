/* Inline field-help — ? buttons that show instruction popovers. */

/** Currently open popover element (if any). */
let activePopover = null;

/**
 * Close any open help popover.
 */
function closeActivePopover() {
  if (activePopover) {
    activePopover.remove();
    activePopover = null;
  }
  document.querySelectorAll('.help-btn.active').forEach((b) => b.classList.remove('active'));
}

/**
 * Toggle help popover for a given field.
 * @param {HTMLElement} btn  - the ? button clicked
 * @param {string} helpHtml  - rich HTML content to display
 */
export function toggleHelp(btn, helpHtml) {
  // If this button's popover is already open, close it.
  if (btn.classList.contains('active')) {
    closeActivePopover();
    return;
  }

  // Close any other open popover first.
  closeActivePopover();

  // Create popover element.
  const popover = document.createElement('div');
  popover.className = 'field-help-popover';
  popover.innerHTML = helpHtml;
  activePopover = popover;

  // Insert after the label row, positioned absolutely over the content below.
  const field = btn.closest('.field');
  const labelRow = btn.closest('.label-row');
  if (labelRow) {
    labelRow.after(popover);
  } else {
    const desc = field.querySelector('.field-desc');
    if (desc) desc.after(popover);
    else field.prepend(popover);
  }

  btn.classList.add('active');

  // Trigger entry animation on next frame.
  requestAnimationFrame(() => popover.classList.add('visible'));
}

/**
 * Initialize global click handler to close popovers when clicking outside.
 * Call once on DOMContentLoaded. Help buttons are created dynamically by
 * schema-renderer.js and wire their own click → toggleHelp() listeners.
 */
export function initHelpPopovers() {
  document.addEventListener('click', (e) => {
    if (!activePopover) return;
    if (e.target.closest('.field-help-popover')) return;
    if (e.target.closest('.help-btn')) return;
    // Keep open if clicking interactive elements within the owning field.
    const ownerField = activePopover.closest('.field');
    if (ownerField && ownerField.contains(e.target) && e.target.closest('input, select, button, .secret-row')) return;
    closeActivePopover();
  });
}
