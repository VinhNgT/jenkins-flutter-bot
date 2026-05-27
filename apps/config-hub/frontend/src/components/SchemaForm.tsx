/**
 * SchemaForm — Dynamic configuration form rendered from service schemas.
 *
 * Fetches schema + current config values, renders grouped form fields,
 * and handles save/reload with deep merge semantics.
 *
 * Field naming convention: `scope:dotted.key` (e.g. `bot:telegram.bot_token`).
 * Secret fields use a set/change flow to avoid accidentally clearing values.
 */

import { Save, RotateCcw } from 'lucide-preact';
import { useCallback, useEffect, useRef, useState } from 'preact/hooks';
import { API } from '../api';
import { useToast } from '../context/ToastContext';
import type { Schema, SchemaField, Scope, ScopeConfig } from '../types';

interface SchemaFormProps {
  scope: Scope;
  schema: Schema;
  config: ScopeConfig | null;
  onConfigReload: () => void;
}

const SCOPE_LABELS: Record<Scope, string> = {
  bot: 'Bot',
  agent: 'Agent',
  file_manager: 'File Manager',
  builds: 'Build Manager',
};

export default function SchemaForm({
  scope,
  schema,
  config,
  onConfigReload,
}: SchemaFormProps) {
  const { showToast } = useToast();
  const formRef = useRef<HTMLFormElement>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);

  // Track which secrets are in "editing" mode
  const [editingSecrets, setEditingSecrets] = useState<Set<string>>(new Set());

  // Reset dirty state when config reloads
  useEffect(() => {
    setDirty(false);
    setEditingSecrets(new Set());
  }, [config]);

  // Group fields by their group property
  const groups = new Map<string, SchemaField[]>();
  for (const field of schema.fields) {
    const existing = groups.get(field.group);
    if (existing) {
      existing.push(field);
    } else {
      groups.set(field.group, [field]);
    }
  }

  /** Get the current value for a field from config. */
  function getFieldValue(key: string): string {
    if (!config?.values) return '';
    // Keys are dot-separated: "telegram.bot_token" → config.values.telegram.bot_token
    const parts = key.split('.');
    let current: unknown = config.values;
    for (const part of parts) {
      if (current && typeof current === 'object' && part in current) {
        current = (current as Record<string, unknown>)[part];
      } else {
        return '';
      }
    }
    return current != null ? String(current) : '';
  }

  /** Check if a secret field has a stored value. */
  function isSecretSet(key: string): boolean {
    if (!config?.secret_lengths) return false;
    const parts = key.split('.');
    let current: unknown = config.secret_lengths;
    for (const part of parts) {
      if (current && typeof current === 'object' && part in current) {
        current = (current as Record<string, unknown>)[part];
      } else {
        return false;
      }
    }
    return typeof current === 'number' && current > 0;
  }

  /** Build save payload from form data. */
  const buildPayload = useCallback(() => {
    if (!formRef.current) return {};

    const formData = new FormData(formRef.current);
    const payload: Record<string, unknown> = {};

    for (const [name, value] of formData.entries()) {
      const [, key] = name.split(':', 2);
      if (!key) continue;

      const strValue = String(value).trim();
      if (strValue === '') continue; // Skip empty — preserves existing via deep_merge

      // Build nested structure from dotted key
      const parts = key.split('.');
      let target: Record<string, unknown> = payload;
      for (let i = 0; i < parts.length - 1; i++) {
        const part = parts[i]!;
        if (!(part in target)) target[part] = {};
        target = target[part] as Record<string, unknown>;
      }
      target[parts[parts.length - 1]!] = strValue;
    }

    return payload;
  }, []);

  async function handleSave() {
    const payload = buildPayload();
    setSaving(true);
    const result = await API.saveScope(scope, payload);
    setSaving(false);

    if (result) {
      showToast(`${SCOPE_LABELS[scope]} config saved`, 'success');
      setDirty(false);
      onConfigReload();
    } else {
      showToast(`Failed to save ${SCOPE_LABELS[scope]} config`, 'error');
    }
  }

  async function handleReload() {
    onConfigReload();
    showToast(`${SCOPE_LABELS[scope]} config reloaded`, 'info');
  }

  function toggleSecretEdit(key: string) {
    setEditingSecrets((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
    setDirty(true);
  }

  return (
    <div>
      <h2 class="panel-title">{schema.title}</h2>
      <p class="panel-desc" dangerouslySetInnerHTML={{ __html: schema.description }} />

      <form
        ref={formRef}
        onInput={() => setDirty(true)}
        onChange={() => setDirty(true)}
        onSubmit={(e) => {
          e.preventDefault();
          handleSave();
        }}
      >
        {[...groups.entries()].map(([groupName, fields]) => (
          <div class="card" key={groupName} style={{ marginBottom: '10px' }}>
            <h3>{groupName}</h3>
            <div class="form-grid" data-scope={scope}>
              {fields.map((field) => (
                <FieldRenderer
                  key={field.key}
                  scope={scope}
                  field={field}
                  value={getFieldValue(field.key)}
                  secretSet={field.secret ? isSecretSet(field.key) : false}
                  editing={editingSecrets.has(field.key)}
                  onToggleEdit={() => toggleSecretEdit(field.key)}
                />
              ))}
            </div>
          </div>
        ))}

        <div class={`form-actions${dirty ? ' scope-dirty' : ''}`}>
          <button
            type="submit"
            class="btn btn-accent"
            disabled={saving}
          >
            <Save class="icon" size={14} />
            Save {SCOPE_LABELS[scope]} Config
            <span class="save-dot" />
          </button>
          <button
            type="button"
            class="btn btn-secondary"
            onClick={handleReload}
          >
            <RotateCcw class="icon" size={14} />
            Reload
          </button>
        </div>
      </form>
    </div>
  );
}

/* ─── Individual Field Renderer ───────────────────────────────── */

interface FieldRendererProps {
  scope: Scope;
  field: SchemaField;
  value: string;
  secretSet: boolean;
  editing: boolean;
  onToggleEdit: () => void;
}

function FieldRenderer({
  scope,
  field,
  value,
  secretSet,
  editing,
  onToggleEdit,
}: FieldRendererProps) {
  const [helpOpen, setHelpOpen] = useState(false);
  const name = `${scope}:${field.key}`;

  const isSecretLocked = field.secret && secretSet && !editing;

  return (
    <div
      class={`field${field.secret ? ' field--secret' : ''}${field.full_width ? ' field--full' : ''}`}
    >
      {/* Label + optional help button */}
      {field.help_html ? (
        <div class="label-row">
          <label>
            {field.label}
            {field.required && <span class="required-marker"> *</span>}
          </label>
          <button
            type="button"
            class={`help-btn${helpOpen ? ' active' : ''}`}
            aria-label="Show help"
            onClick={(e) => {
              e.stopPropagation();
              setHelpOpen(!helpOpen);
            }}
          >
            ?
          </button>
        </div>
      ) : (
        <label>
          {field.label}
          {field.required && <span class="required-marker"> *</span>}
        </label>
      )}

      {/* Help popover */}
      {field.help_html && helpOpen && (
        <div
          class="field-help-popover visible"
          dangerouslySetInnerHTML={{ __html: field.help_html }}
        />
      )}

      {/* Description */}
      {field.description && <p class="field-desc">{field.description}</p>}

      {/* Input */}
      {field.secret ? (
        <div class="secret-row">
          <input
            type="password"
            name={name}
            autocomplete="off"
            disabled={isSecretLocked}
            placeholder={
              isSecretLocked
                ? `••••••••  (${secretSet ? 'set' : 'not set'})`
                : field.placeholder ?? ''
            }
          />
          {secretSet && !editing && (
            <button
              type="button"
              class="btn btn-sm btn-secondary"
              onClick={onToggleEdit}
            >
              Change
            </button>
          )}
          {editing && (
            <button
              type="button"
              class="btn btn-sm btn-secondary"
              onClick={onToggleEdit}
            >
              Reset
            </button>
          )}
        </div>
      ) : field.type === 'select' && field.options ? (
        <select name={name}>
          {field.options.map((opt) => (
            <option
              key={opt}
              value={opt}
              selected={value.toLowerCase() === opt.toLowerCase()}
            >
              {opt}
            </option>
          ))}
        </select>
      ) : (
        <input
          name={name}
          type={field.type === 'integer' ? 'number' : 'text'}
          min={field.type === 'integer' ? '0' : undefined}
          value={value}
          placeholder={
            field.default != null ? String(field.default) : field.placeholder ?? ''
          }
        />
      )}
    </div>
  );
}
