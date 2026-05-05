/* Inline field-help — ? buttons that show instruction popovers. */

/**
 * Help text keyed by field name attribute (e.g. "bot:telegram.bot_token").
 * Content is rich HTML migrated from the former Setup Wizard steps.
 */
const FIELD_HELP = {
  // ── Telegram Bot ──
  'bot:telegram.bot_token':
    'Open Telegram → search for <strong>@BotFather</strong> → send <code>/newbot</code> → follow the prompts. Copy the token it gives you.',

  'bot:telegram.allowed_chat_ids':
    'Send any message to your bot, then open <code>https://api.telegram.org/bot&lt;TOKEN&gt;/getUpdates</code> in a browser. Look for <code>"chat":{"id":…}</code>. Comma-separate multiple IDs.',

  'bot:jenkins.api_token':
    'In Jenkins: click your username (top-right) → <strong>Configure</strong> → <strong>API Token</strong> → <strong>Add new Token</strong> → copy the generated token.',

  // ── Jenkins Agent ──
  'agent:agent.name':
    'Must exactly match the node name in Jenkins. Create the node: <strong>Manage Jenkins</strong> → <strong>Nodes</strong> → <strong>New Node</strong> → name it (e.g. <code>flutter-agent</code>).',

  'agent:agent.secret':
    'After creating the node in Jenkins, go to <strong>Nodes</strong> → click the agent name → the secret is shown on the status page under the connection command. Copy the long hex string.',

  // ── Google Drive ──
  'ui:drive.client_id':
    'Go to <a href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noopener">Google Cloud Console → APIs &amp; Services → Credentials</a> → <strong>Create Credentials</strong> → <strong>OAuth client ID</strong> → Application type: <strong>Web application</strong>. Add <code>http://&lt;your-host&gt;:9000/api/drive/oauth/callback</code> as an authorized redirect URI. Copy the Client ID.',

  'ui:drive.client_secret':
    'Shown on the same credentials page as the Client ID. Click the OAuth client you just created to view the secret.',
};

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
function toggleHelp(btn, helpHtml) {
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
 * Inject ? buttons into every config field that has help text.
 * Call once on DOMContentLoaded.
 */
// eslint-disable-next-line no-unused-vars
function initHelpButtons() {
  // Walk every input/select with a name attribute inside config panels.
  document.querySelectorAll('.tab-panel .field').forEach((field) => {
    // Find the input or select inside this field.
    const input = field.querySelector('input[name], select[name]');
    if (!input) return;

    const name = input.getAttribute('name');
    const helpHtml = FIELD_HELP[name];
    if (!helpHtml) return;

    // Create the ? button.
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'help-btn';
    btn.setAttribute('aria-label', 'Show help');
    btn.textContent = '?';

    // Wrap label + button in a flex row so the button is a sibling,
    // not a child of the label (avoids label clicks triggering help).
    const label = field.querySelector('label');
    if (label) {
      const row = document.createElement('div');
      row.className = 'label-row';
      label.before(row);
      row.appendChild(label);
      row.appendChild(btn);
    }

    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleHelp(btn, helpHtml);
    });
  });

  // Close popover when clicking outside.
  // Keep open only when interacting with the input/select in the same field.
  document.addEventListener('click', (e) => {
    if (!activePopover) return;
    if (e.target.closest('.field-help-popover')) return;
    if (e.target.closest('.help-btn')) return;
    // Keep open if clicking the input or select within the owning field.
    const ownerField = activePopover.closest('.field');
    if (ownerField && (e.target.closest('input') || e.target.closest('select')) && ownerField.contains(e.target)) return;
    closeActivePopover();
  });
}
