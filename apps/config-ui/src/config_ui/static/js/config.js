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
 * Collect form data for a single scope. Secret fields are only included
 * if the user explicitly clicked "Change" (marked by data-changed).
 * @param {string} scope - 'bot', 'agent', or 'ui'
 * @returns {Object}
 */
// eslint-disable-next-line no-unused-vars
function collectScope(scope) {
  const data = {};
  document.querySelectorAll(`[data-scope="${scope}"] input[name], [data-scope="${scope}"] select[name]`).forEach((el) => {
    // Skip secret fields that weren't explicitly edited
    const secretField = el.closest('.field--secret');
    if (secretField && !secretField.hasAttribute('data-changed')) return;

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
      // Reset secret field state
      secretField.removeAttribute('data-changed');
      const isSet = secretsSet && secretsSet[dottedKey];
      if (isSet) {
        secretField.removeAttribute('data-not-set');
        secretField.querySelector('.secret-display').hidden = false;
        secretField.querySelector('.secret-edit').hidden = true;
      } else {
        secretField.setAttribute('data-not-set', '');
        secretField.querySelector('.secret-display').hidden = true;
        secretField.querySelector('.secret-edit').hidden = false;
      }
      el.value = '';
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
 * For secret fields, a field counts as valid if it already has a stored
 * value (data-not-set is absent) even if the user hasn't typed a new one.
 * @param {string} scope
 * @returns {{ valid: boolean, missing: string[] }}
 */
// eslint-disable-next-line no-unused-vars
function validateScope(scope) {
  const missing = [];
  document.querySelectorAll(`[data-scope="${scope}"] .field[data-required]`).forEach((field) => {
    const input = field.querySelector('input[name], select[name]');
    if (!input) return;

    const secretField = field.closest('.field--secret');
    if (secretField) {
      // Secret is valid if it's already stored OR the user entered a new value
      const alreadySet = !secretField.hasAttribute('data-not-set');
      const hasNewValue = secretField.hasAttribute('data-changed') && input.value.trim() !== '';
      if (!alreadySet && !hasNewValue) {
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

    const action = btn.dataset.action;
    if (action === 'change-secret') {
      field.querySelector('.secret-display').hidden = true;
      field.querySelector('.secret-edit').hidden = false;
      field.setAttribute('data-changed', '');
      const input = field.querySelector('.secret-edit input');
      if (input) input.focus();
    } else if (action === 'cancel-secret') {
      field.querySelector('.secret-display').hidden = false;
      field.querySelector('.secret-edit').hidden = true;
      field.removeAttribute('data-changed');
      const input = field.querySelector('.secret-edit input');
      if (input) input.value = '';
    }
  });
}
