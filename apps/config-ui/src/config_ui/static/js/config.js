/* Form data helpers — collect and populate config fields. */

function nestedSet(target, dottedKey, value) {
  const parts = dottedKey.split('.');
  let current = target;
  for (const part of parts.slice(0, -1)) {
    if (!(part in current) || typeof current[part] !== 'object') {
      current[part] = {};
    }
    current = current[part];
  }
  current[parts[parts.length - 1]] = value;
}

function nestedGet(target, dottedKey) {
  return dottedKey.split('.').reduce((value, part) => {
    if (!value || typeof value !== 'object') return '';
    return value[part] ?? '';
  }, target);
}

/**
 * Collect form data for a single scope. Disabled secret inputs (stored,
 * unchanged) are skipped so existing values are preserved on the backend.
 * @param {string} scope - 'bot', 'agent', or 'ui'
 * @returns {Object}
 */
// eslint-disable-next-line no-unused-vars
function collectScope(scope) {
  const data = {};
  document.querySelectorAll(`[data-scope="${scope}"] input[name], [data-scope="${scope}"] select[name]`).forEach((el) => {
    // Skip secret fields whose value is stored and unchanged (disabled)
    if (el.closest('.field--secret') && el.disabled) return;

    const dottedKey = el.name.split(':')[1];
    if (dottedKey) {
      nestedSet(data, dottedKey, el.value);
    }
  });
  return data;
}

/**
 * Populate form fields for a scope from API response data.
 * @param {string} scope
 * @param {Object} data - config data for this scope
 * @param {Object} secretsSet - { "dotted.key": bool } for this scope
 * @param {Object} [defaults] - { "dotted.key": "default_value" } for this scope
 */
// eslint-disable-next-line no-unused-vars
function populateScope(scope, data, secretsSet, defaults) {
  document.querySelectorAll(`[data-scope="${scope}"] input[name], [data-scope="${scope}"] select[name]`).forEach((el) => {
    const dottedKey = el.name.split(':')[1];
    if (!dottedKey) return;

    const secretField = el.closest('.field--secret');
    if (secretField) {
      const secretLen = secretsSet && secretsSet[dottedKey];
      const changeBtn = secretField.querySelector('[data-action="change-secret"]');
      const cancelBtn = secretField.querySelector('[data-action="cancel-secret"]');
      el.value = '';
      if (secretLen) {
        el.disabled = true;
        el.placeholder = '\u2022'.repeat(secretLen);
        if (changeBtn) { changeBtn.textContent = 'Change'; changeBtn.hidden = false; }
        if (cancelBtn) cancelBtn.hidden = true;
      } else {
        el.disabled = true;
        el.placeholder = '';
        if (changeBtn) { changeBtn.textContent = 'Set'; changeBtn.hidden = false; }
        if (cancelBtn) cancelBtn.hidden = true;
      }
    } else {
      const value = nestedGet(data || {}, dottedKey);
      const strValue = value !== null && value !== undefined ? String(value) : '';

      if (el.tagName === 'SELECT') {
        // For selects: use the config value if set, otherwise fall back to default
        if (strValue) {
          el.value = strValue;
        } else {
          const defaultValue = defaults && defaults[dottedKey];
          if (defaultValue) {
            el.value = defaultValue;
          }
        }
      } else {
        el.value = strValue;
      }

      // Set placeholder from defaults (shows hint when field is empty)
      if (defaults && defaults[dottedKey]) {
        el.placeholder = defaults[dottedKey];
      }
    }
  });
}

/**
 * Mark required fields within a scope by adding an asterisk to their label
 * and a data-required attribute to the .field container.
 * @param {string} scope
 * @param {string[]} requiredKeys - dotted keys that are required
 */
function markRequired(scope, requiredKeys) {
  if (!requiredKeys || !requiredKeys.length) return;
  const keySet = new Set(requiredKeys);
  document.querySelectorAll(`[data-scope="${scope}"] input[name], [data-scope="${scope}"] select[name]`).forEach((el) => {
    const dottedKey = el.name.split(':')[1];
    if (!dottedKey || !keySet.has(dottedKey)) return;

    const field = el.closest('.field');
    if (!field) return;
    field.setAttribute('data-required', '');

    // Add asterisk to label if not already present
    const label = field.querySelector('label');
    if (label && !label.querySelector('.required-marker')) {
      const marker = document.createElement('span');
      marker.className = 'required-marker';
      marker.textContent = ' *';
      label.appendChild(marker);
    }
  });
}

/**
 * Validate that all required fields for a scope have values.
 * For secret fields, a disabled input means the value is stored on the
 * backend (valid).  An enabled input must contain a non-empty value.
 * @param {string} scope
 * @returns {{ valid: boolean, missing: string[] }}
 */
// eslint-disable-next-line no-unused-vars
function validateScope(scope) {
  const missing = [];
  document.querySelectorAll(`[data-scope="${scope}"] .field[data-required]`).forEach((field) => {
    const input = field.querySelector('input[name], select[name]');
    if (!input) return;

    if (input.closest('.field--secret')) {
      // Disabled with a placeholder means the value is stored on the backend
      const isStored = input.disabled && input.placeholder;
      if (!isStored && !input.value.trim()) {
        missing.push(field.querySelector('label')?.textContent?.replace(' *', '') || input.name);
      }
    } else {
      if (!input.value.trim()) {
        missing.push(field.querySelector('label')?.textContent?.replace(' *', '') || input.name);
      }
    }
  });
  return { valid: missing.length === 0, missing };
}

/**
 * Populate all scopes from the full GET /api/config response.
 * @param {Object} response - { bot, agent, ui, _secrets_set, _defaults, _required }
 */
// eslint-disable-next-line no-unused-vars
function populateAll(response) {
  if (!response) return;
  const defaults = response._defaults || {};
  const required = response._required || {};
  populateScope('bot', response.bot, response._secrets_set?.bot, defaults.bot);
  populateScope('agent', response.agent, response._secrets_set?.agent, defaults.agent);
  populateScope('ui', response.ui, response._secrets_set?.ui, defaults.ui);
  markRequired('bot', required.bot);
  markRequired('agent', required.agent);
  markRequired('ui', required.ui);
}

/**
 * Initialize secret field Change/Cancel toggle logic.
 */
// eslint-disable-next-line no-unused-vars
function initSecretFields() {
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;

    const field = btn.closest('.field--secret');
    if (!field) return;

    const input = field.querySelector('input[name]');
    const changeBtn = field.querySelector('[data-action="change-secret"]');
    const cancelBtn = field.querySelector('[data-action="cancel-secret"]');

    if (btn.dataset.action === 'change-secret') {
      field.dataset.prevPlaceholder = input.placeholder;
      input.disabled = false;
      input.value = '';
      input.placeholder = '';
      input.focus();
      if (changeBtn) changeBtn.hidden = true;
      if (cancelBtn) cancelBtn.hidden = false;
    } else if (btn.dataset.action === 'cancel-secret') {
      input.disabled = true;
      input.value = '';
      input.placeholder = 'prevPlaceholder' in field.dataset ? field.dataset.prevPlaceholder : '\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022';
      if (changeBtn) changeBtn.hidden = false;
      if (cancelBtn) cancelBtn.hidden = true;
    }
  });
}
