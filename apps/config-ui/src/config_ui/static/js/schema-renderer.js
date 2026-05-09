/* Dynamic config form rendering from module schemas. */



const SCOPE_LABELS = { bot: 'Bot', agent: 'Agent', ui: 'Drive' };

/**
 * Render a config form panel from a module schema.
 * @param {string} containerId  - target div id (e.g. "schema-container-bot")
 * @param {string} scope        - "bot", "agent", or "ui"
 * @param {Object} schema       - { title, description, fields: [...] }
 */
// eslint-disable-next-line no-unused-vars
function renderSchemaForm(containerId, scope, schema) {
  const container = document.getElementById(containerId);
  if (!container || !schema) return;

  container.innerHTML = '';

  // Panel title + description
  const title = document.createElement('h2');
  title.className = 'panel-title';
  title.textContent = schema.title;
  container.appendChild(title);

  const desc = document.createElement('p');
  desc.className = 'panel-desc';
  desc.innerHTML = schema.description;
  container.appendChild(desc);

  // Group fields by their "group" property (preserve insertion order)
  const groups = new Map();
  for (const field of schema.fields) {
    if (!groups.has(field.group)) groups.set(field.group, []);
    groups.get(field.group).push(field);
  }

  // Render each group as a card
  for (const [groupName, fields] of groups) {
    const card = document.createElement('div');
    card.className = 'card';

    const h3 = document.createElement('h3');
    h3.textContent = groupName;
    card.appendChild(h3);

    const grid = document.createElement('div');
    grid.className = 'form-grid';
    grid.dataset.scope = scope;

    for (const field of fields) {
      grid.appendChild(_renderField(scope, field));
    }

    card.appendChild(grid);
    container.appendChild(card);
  }

  // Save + Reload actions
  const label = SCOPE_LABELS[scope] || scope;
  const actions = document.createElement('div');
  actions.className = 'form-actions';
  actions.innerHTML = `
    <button class="btn btn-accent" data-save="${scope}" type="button">${Icons.save}Save ${label} Config</button>
    <button class="btn btn-secondary" data-reload="${scope}" type="button">${Icons.restart}Reload</button>
  `;
  container.appendChild(actions);
}

/**
 * Render a single field element from a schema field definition.
 * @param {string} scope
 * @param {Object} f - field definition from schema
 * @returns {HTMLElement}
 */
function _renderField(scope, f) {
  const fieldDiv = document.createElement('div');
  fieldDiv.className = f.secret ? 'field field--secret' : 'field';
  if (f.secret) fieldDiv.dataset.secretKey = f.key;
  if (f.required) fieldDiv.dataset.required = '';

  // Label
  const label = document.createElement('label');
  label.textContent = f.label;
  if (f.required) {
    const marker = document.createElement('span');
    marker.className = 'required-marker';
    marker.textContent = ' *';
    label.appendChild(marker);
  }

  // Help button (only if help_html is provided)
  if (f.help_html) {
    const row = document.createElement('div');
    row.className = 'label-row';
    row.appendChild(label);

    const helpBtn = document.createElement('button');
    helpBtn.type = 'button';
    helpBtn.className = 'help-btn';
    helpBtn.setAttribute('aria-label', 'Show help');
    helpBtn.textContent = '?';
    helpBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleHelp(helpBtn, f.help_html);
    });
    row.appendChild(helpBtn);
    fieldDiv.appendChild(row);
  } else {
    fieldDiv.appendChild(label);
  }

  // Description
  if (f.description) {
    const desc = document.createElement('p');
    desc.className = 'field-desc';
    desc.textContent = f.description;
    fieldDiv.appendChild(desc);
  }

  // Input element
  const name = `${scope}:${f.key}`;
  if (f.secret) {
    const secretRow = document.createElement('div');
    secretRow.className = 'secret-row';

    const input = document.createElement('input');
    input.type = 'password';
    input.name = name;
    input.autocomplete = 'off';
    secretRow.appendChild(input);

    const changeBtn = document.createElement('button');
    changeBtn.type = 'button';
    changeBtn.className = 'btn btn-sm btn-secondary';
    changeBtn.dataset.action = 'change-secret';
    changeBtn.textContent = 'Change';
    secretRow.appendChild(changeBtn);

    const cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.className = 'btn btn-sm btn-secondary';
    cancelBtn.dataset.action = 'cancel-secret';
    cancelBtn.hidden = true;
    cancelBtn.textContent = 'Reset';
    secretRow.appendChild(cancelBtn);

    fieldDiv.appendChild(secretRow);
  } else if (f.field_type === 'select' && f.choices && f.choices.length) {
    const select = document.createElement('select');
    select.name = name;
    for (const [value, text] of f.choices) {
      const opt = document.createElement('option');
      opt.value = value;
      opt.textContent = text;
      select.appendChild(opt);
    }
    fieldDiv.appendChild(select);
  } else {
    const input = document.createElement('input');
    input.name = name;
    if (f.field_type === 'number') {
      input.type = 'number';
      input.min = '0';
    }
    if (f.default) {
      input.placeholder = f.default;
    }
    fieldDiv.appendChild(input);
  }

  return fieldDiv;
}
