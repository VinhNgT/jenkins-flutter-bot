/**
 * SchemaForm — Dynamic configuration form rendered from service schemas.
 *
 * Fetches schema + current config values, renders grouped form fields,
 * and handles save/reload with deep merge semantics.
 *
 * Field naming convention: `scope:dotted.key` (e.g. `bot:telegram.bot_token`).
 * Secret fields use a set/change flow to avoid accidentally clearing values.
 */

import { Save, RotateCcw, Plus, Trash2 } from 'lucide-preact';
import { useCallback, useEffect, useRef, useState } from 'preact/hooks';
import { API } from '../api';
import { useToast } from '../context/ToastContext';
import type { Schema, SchemaField, Scope, ScopeConfig } from '../types';

interface SchemaFormProps {
  scope: Scope;
  schema: Schema;
  config: ScopeConfig | null;
  onConfigReload: () => void;
  onDirtyChange?: (scope: Scope, isDirty: boolean) => void;
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
  onDirtyChange,
}: SchemaFormProps) {
  const { showToast } = useToast();
  const formRef = useRef<HTMLFormElement>(null);
  const [dirty, setDirty] = useState(false);
  const [dirtyFields, setDirtyFields] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);
  const [saveAttempted, setSaveAttempted] = useState(false);

  // Track which secrets are in "editing" mode
  const [editingSecrets, setEditingSecrets] = useState<Set<string>>(new Set());

  // Reset dirty state when config reloads
  useEffect(() => {
    setDirty(false);
    setDirtyFields(new Set());
    setEditingSecrets(new Set());
    setSaveAttempted(false);
  }, [config]);

  // Notify parent on dirty changes
  useEffect(() => {
    onDirtyChange?.(scope, dirty);
  }, [scope, dirty, onDirtyChange]);

  /** Get the set of dirty fields by comparing current values with original config values. */
  const getDirtyFields = useCallback((currentEditingSecrets?: Set<string>) => {
    const dirtySet = new Set<string>();
    if (!formRef.current) return dirtySet;

    // Check custom VPN file changes
    if (scope === 'agent') {
      const pending = !!(window as unknown as Record<string, File | null>).pendingVpnFile;
      if (pending) {
        dirtySet.add('vpn_file');
      }
    }

    // Check editing secrets
    const activeSecrets = currentEditingSecrets ?? editingSecrets;
    for (const secretKey of activeSecrets) {
      dirtySet.add(secretKey);
    }

    // Check standard inputs, selects and secrets
    for (const field of schema.fields) {
      const input = formRef.current.querySelector(`[name="${scope}:${field.key}"]`) as HTMLInputElement | HTMLSelectElement | null;
      if (!input) continue;

      if (field.secret) {
        const current = input.value;
        const isEditing = activeSecrets.has(field.key);
        if (current.length > 0 || isEditing) {
          dirtySet.add(field.key);
        }
        continue;
      }

      const original = getFieldValue(field.key);
      const current = input.value.trim();

      // Normalize boolean check to prevent false-dirty states
      if (field.type === 'boolean') {
        const origBool =
          original.toLowerCase() === 'true' ||
          (original === '' &&
            (field.default === true ||
              String(field.default).toLowerCase() === 'true'));
        const currBool = current.toLowerCase() === 'true';
        if (origBool !== currBool) {
          dirtySet.add(field.key);
        }
        continue;
      }

      if (field.field_type === 'key_value') {
        try {
          const origObj = JSON.parse(original || '{}');
          const currObj = JSON.parse(current || '{}');
          const origSorted = JSON.stringify(origObj, Object.keys(origObj).sort());
          const currSorted = JSON.stringify(currObj, Object.keys(currObj).sort());
          if (origSorted !== currSorted) {
            dirtySet.add(field.key);
          }
        } catch {
          if (current !== original.trim()) {
            dirtySet.add(field.key);
          }
        }
        continue;
      }

      if (current !== original.trim()) {
        dirtySet.add(field.key);
      }
    }

    return dirtySet;
  }, [scope, schema, config, editingSecrets]);

  const updateDirtyStates = useCallback((currentEditingSecrets?: Set<string>) => {
    const fields = getDirtyFields(currentEditingSecrets);
    setDirtyFields(fields);
    setDirty(fields.size > 0);
  }, [getDirtyFields]);

  // Listen to custom VPN file changes to mark form as dirty
  useEffect(() => {
    if (scope !== 'agent') return;
    const handleVpnChange = () => {
      updateDirtyStates();
    };
    window.addEventListener('vpn-file-change', handleVpnChange);
    return () => window.removeEventListener('vpn-file-change', handleVpnChange);
  }, [scope, updateDirtyStates]);

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
    if (current == null) return '';
    if (typeof current === 'object') {
      return JSON.stringify(current);
    }
    return String(current);
  }

  /** Check if a secret field has a stored value. */
  function isSecretSet(key: string): boolean {
    if (!config?.secret_lengths) return false;
    const current = config.secret_lengths[key];
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
    setSaveAttempted(true);

    if (formRef.current) {
      const invalidInput = formRef.current.querySelector('input[data-invalid="true"]');
      if (invalidInput) {
        showToast('Please resolve all validation errors in Build Options before saving.', 'error');
        return;
      }

      if (!formRef.current.checkValidity()) {
        formRef.current.reportValidity();
        showToast('Please resolve all validation errors before saving.', 'error');
        return;
      }
    }

    const payload = buildPayload();
    setSaving(true);
    const result = await API.saveScope(scope, payload);

    if (result) {
      // If we are in the 'agent' scope and there is a pending VPN file, upload it!
      const pendingVpnFile = (window as unknown as Record<string, File | null>).pendingVpnFile;
      if (scope === 'agent' && pendingVpnFile) {
        try {
          const formData = new FormData();
          formData.append('file', pendingVpnFile);

          const uploadRes = await fetch('/api/services/agent/vpn/upload', {
            method: 'POST',
            body: formData,
          });

          if (!uploadRes.ok) {
            const errBody = await uploadRes.json().catch(() => ({}));
            throw new Error(errBody.detail ?? `HTTP ${uploadRes.status}`);
          }

          showToast('OpenVPN configuration file uploaded successfully', 'success');

          // Clear pending file from widget
          const clearPendingVpnFile = (window as unknown as Record<string, (() => void) | null>).clearPendingVpnFile;
          if (clearPendingVpnFile) {
            clearPendingVpnFile();
          }
          (window as unknown as Record<string, unknown>).pendingVpnFile = null;

          // Refresh VPN widget
          const refreshVpnWidgetStatus = (window as unknown as Record<string, (() => Promise<void>) | null>).refreshVpnWidgetStatus;
          if (refreshVpnWidgetStatus) {
            await refreshVpnWidgetStatus();
          }
        } catch (err) {
          showToast(`Failed to upload OpenVPN configuration: ${(err as Error).message}`, 'error');
          setSaving(false);
          return;
        }
      }

      showToast(`${SCOPE_LABELS[scope]} config saved`, 'success');
      setDirty(false);
      setSaveAttempted(false);
      onConfigReload();
    } else {
      showToast(`Failed to save ${SCOPE_LABELS[scope]} config`, 'error');
    }
    setSaving(false);
  }

  async function handleReload() {
    onConfigReload();
    showToast(`${SCOPE_LABELS[scope]} config reloaded`, 'info');
  }

  function toggleSecretEdit(key: string) {
    setEditingSecrets((prev) => {
      const next = new Set(prev);
      const isRemoving = next.has(key);
      if (isRemoving) {
        next.delete(key);
        // Clear the password input value in the DOM when cancelling
        if (formRef.current) {
          const input = formRef.current.querySelector(`input[name="${scope}:${key}"]`) as HTMLInputElement | null;
          if (input) {
            input.value = '';
          }
        }
      } else {
        next.add(key);
      }
      // Re-evaluate dirty state after the set is updated
      setTimeout(() => {
        updateDirtyStates(next);
      }, 0);
      return next;
    });
  }

  return (
    <div>
      <h2 class="panel-title">{schema.title}</h2>
      <p class="panel-desc" dangerouslySetInnerHTML={{ __html: schema.description }} />

      <form
        ref={formRef}
        class={saveAttempted ? 'save-attempted' : ''}
        onInput={() => {
          updateDirtyStates();
          setSaveAttempted(false);
        }}
        onChange={() => {
          updateDirtyStates();
          setSaveAttempted(false);
        }}
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
                  isDirty={dirtyFields.has(field.key)}
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

/* ─── Interactive Key-Value Rows Editor Component ──────────────── */

interface KeyValueRow {
  id: string;
  key: string;
  value: string;
}

interface KeyValueEditorProps {
  name: string;
  value: string;
}

function KeyValueEditor({ name, value }: KeyValueEditorProps) {
  const initialRowsRef = useRef<KeyValueRow[]>([]);
  const [rows, setRows] = useState<KeyValueRow[]>(() => {
    let initial: KeyValueRow[] = [];
    try {
      const parsed = JSON.parse(value || '{}');
      if (typeof parsed === 'object' && parsed !== null) {
        initial = Object.entries(parsed).map(([k, v]) => ({
          id: Math.random().toString(36).substring(2, 9),
          key: k,
          value: String(v),
        }));
      }
    } catch {
      if (value && typeof value === 'string') {
        const items = value.split(',').map(item => item.trim()).filter(Boolean);
        initial = items.map(item => ({
          id: Math.random().toString(36).substring(2, 9),
          key: item,
          value: item,
        }));
      }
    }
    initialRowsRef.current = initial;
    return initial;
  });

  const hiddenInputRef = useRef<HTMLInputElement>(null);

  // Sync rows state to serialized JSON in the hidden input
  useEffect(() => {
    if (hiddenInputRef.current) {
      const obj: Record<string, string> = {};
      let isLocalInvalid = false;
      const keysSeen = new Set<string>();

      for (const row of rows) {
        const trimmedKey = row.key.trim();
        const trimmedVal = row.value.trim();

        // If either is filled but not both, it is incomplete
        if ((trimmedKey && !trimmedVal) || (!trimmedKey && trimmedVal)) {
          isLocalInvalid = true;
        }

        if (trimmedKey || trimmedVal) {
          const keyLower = trimmedKey.toLowerCase();
          if (trimmedKey && keysSeen.has(keyLower)) {
            isLocalInvalid = true;
          }
          if (trimmedKey) {
            keysSeen.add(keyLower);
          }
          obj[trimmedKey] = trimmedVal;
        }
      }

      hiddenInputRef.current.value = JSON.stringify(obj);

      if (isLocalInvalid) {
        hiddenInputRef.current.setAttribute('data-invalid', 'true');
      } else {
        hiddenInputRef.current.removeAttribute('data-invalid');
      }

      // Trigger onChange event for dirty checking logic in parent form
      hiddenInputRef.current.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }, [rows]);

  const addRow = () => {
    setRows(prev => [
      ...prev,
      {
        id: Math.random().toString(36).substring(2, 9),
        key: '',
        value: '',
      },
    ]);
  };

  const removeRow = (id: string) => {
    setRows(prev => prev.filter(r => r.id !== id));
  };

  const updateRow = (id: string, field: 'key' | 'value', val: string) => {
    setRows(prev =>
      prev.map(r => (r.id === id ? { ...r, [field]: val } : r))
    );
  };

  const hasIncompleteRow = rows.some(
    r => (r.key.trim() && !r.value.trim()) || (!r.key.trim() && r.value.trim())
  );
  const keys = rows.map(r => r.key.trim().toLowerCase()).filter(Boolean);
  const hasDuplicateKeys = keys.length !== new Set(keys).size;

  return (
    <div class={`key-value-editor${hasIncompleteRow || hasDuplicateKeys ? ' has-error' : ''}`}>
      {rows.length === 0 ? (
        <div class="kv-empty-state">
          <p>No build options configured.</p>
          <button type="button" class="btn btn-sm btn-secondary" onClick={addRow}>
            <Plus class="icon" size={12} /> Add First Option
          </button>
        </div>
      ) : (
        <div class="kv-rows-list">
          {rows.map((row) => {
            const initialRow = initialRowsRef.current.find(r => r.id === row.id);
            const isKeyDirty = initialRow 
              ? row.key.trim() !== initialRow.key.trim() 
              : row.key.trim().length > 0;
            const isValueDirty = initialRow 
              ? row.value.trim() !== initialRow.value.trim() 
              : row.value.trim().length > 0;

            return (
              <div class="kv-row" key={row.id}>
                <input
                  type="text"
                  class={`kv-input-key${isKeyDirty ? ' kv-input--dirty' : ''}`}
                  placeholder="Display Label (e.g. Stable Release)"
                  value={row.key}
                  onInput={(e) => updateRow(row.id, 'key', (e.target as HTMLInputElement).value)}
                />
                <span class="kv-arrow">➔</span>
                <input
                  type="text"
                  class={`kv-input-value${isValueDirty ? ' kv-input--dirty' : ''}`}
                  placeholder="Git Branch (e.g. main)"
                  value={row.value}
                  onInput={(e) => updateRow(row.id, 'value', (e.target as HTMLInputElement).value)}
                />
                <button
                  type="button"
                  class="btn-trash"
                  onClick={() => removeRow(row.id)}
                  aria-label="Delete option"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            );
          })}
          <button type="button" class="btn btn-sm btn-secondary btn-kv-add" onClick={addRow}>
            <Plus class="icon" size={12} /> Add Option
          </button>
        </div>
      )}
      {hasIncompleteRow && (
        <div class="kv-validation-error">
          ⚠️ Display labels and git branches cannot be empty.
        </div>
      )}
      {hasDuplicateKeys && (
        <div class="kv-validation-error">
          ⚠️ Display labels must be unique.
        </div>
      )}
      <input
        ref={hiddenInputRef}
        type="hidden"
        name={name}
      />
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
  isDirty: boolean;
}

function FieldRenderer({
  scope,
  field,
  value,
  secretSet,
  editing,
  onToggleEdit,
  isDirty,
}: FieldRendererProps) {
  const [helpOpen, setHelpOpen] = useState(false);
  const name = `${scope}:${field.key}`;

  const isSecretLocked = field.secret && secretSet && !editing;

  // For boolean switch fields
  const isBoolean = field.type === 'boolean';
  
  const getInitialChecked = () => {
    const valLower = (value || '').toLowerCase();
    if (valLower === 'true') return true;
    if (valLower === 'false') return false;
    return (
      field.default === true ||
      String(field.default).toLowerCase() === 'true'
    );
  };

  const [checked, setChecked] = useState(getInitialChecked());
  const hiddenInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setChecked(getInitialChecked());
  }, [value, field.default]);

  const handleToggle = () => {
    const nextChecked = !checked;
    setChecked(nextChecked);
    if (hiddenInputRef.current) {
      hiddenInputRef.current.value = String(nextChecked);
      hiddenInputRef.current.dispatchEvent(new Event('change', { bubbles: true }));
    }
  };

  const isKeyValue = field.field_type === 'key_value';

  if (isKeyValue) {
    return (
      <div
        class={`field field--key-value field--full${isDirty ? ' field--dirty' : ''}`}
      >
        <div class="label-row">
          <label>
            {field.label}
            {field.required && <span class="required-marker"> *</span>}
            {isDirty && <span class="field-dirty-label"> (unsaved)</span>}
          </label>
          {field.help_html && (
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
          )}
        </div>
        {field.help_html && helpOpen && (
          <div
            class="field-help-popover visible"
            dangerouslySetInnerHTML={{ __html: field.help_html }}
          />
        )}
        {field.description && <p class="field-desc">{field.description}</p>}
        <KeyValueEditor name={name} value={value} />
      </div>
    );
  }

  if (isBoolean) {
    return (
      <div
        class={`field field--boolean${field.full_width ? ' field--full' : ''}${isDirty ? ' field--dirty' : ''}`}
      >
        <div
          class="switch-row"
          tabIndex={0}
          role="switch"
          aria-checked={checked}
          onClick={handleToggle}
          onKeyDown={(e) => {
            if (e.key === ' ' || e.key === 'Enter') {
              e.preventDefault();
              handleToggle();
            }
          }}
        >
          <div class="switch-text-group">
            <div class="label-row">
              <label>
                {field.label}
                {field.required && <span class="required-marker"> *</span>}
                {isDirty && <span class="field-dirty-label"> (unsaved)</span>}
              </label>
              {field.help_html && (
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
              )}
            </div>
            {field.help_html && helpOpen && (
              <div
                class="field-help-popover visible"
                dangerouslySetInnerHTML={{ __html: field.help_html }}
              />
            )}
            {field.description && <p class="field-desc">{field.description}</p>}
          </div>

          <div class={`switch-toggle${checked ? ' checked' : ''}`}>
            <span class="switch-slider" />
          </div>
          <input
            ref={hiddenInputRef}
            type="hidden"
            name={name}
            value={checked ? 'true' : 'false'}
          />
        </div>
      </div>
    );
  }

  return (
    <div
      class={`field${field.secret ? ' field--secret' : ''}${field.full_width ? ' field--full' : ''}${isDirty ? ' field--dirty' : ''}`}
    >
      {/* Label + optional help button */}
      {field.help_html ? (
        <div class="label-row">
          <label>
            {field.label}
            {field.required && <span class="required-marker"> *</span>}
            {isDirty && <span class="field-dirty-label"> (unsaved)</span>}
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
          {isDirty && <span class="field-dirty-label"> (unsaved)</span>}
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
            required={field.required && !isSecretLocked}
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
        (() => {
          const matchedOpt = field.options.find(
            (opt) => opt.toLowerCase() === value.toLowerCase()
          ) ?? value;
          const choices = (field as any).choices as [string, string][] | undefined;
          return (
            <select name={name} defaultValue={matchedOpt} required={field.required}>
              {field.options.map((opt) => {
                const label = choices?.find((c) => c[0] === opt)?.[1] ?? opt;
                return (
                  <option key={opt} value={opt}>
                    {label}
                  </option>
                );
              })}
            </select>
          );
        })()
      ) : (
        <input
          name={name}
          type={field.type === 'integer' ? 'number' : 'text'}
          min={field.type === 'integer' ? '0' : undefined}
          defaultValue={value}
          required={field.required}
          placeholder={
            field.default != null ? String(field.default) : field.placeholder ?? ''
          }
        />
      )}
    </div>
  );
}
