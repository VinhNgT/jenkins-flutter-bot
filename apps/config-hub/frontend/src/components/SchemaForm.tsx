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
import { usePlatform } from 'platform-core';
import type { Schema, SchemaField, Scope, ScopeConfig } from '../types';
import FieldRenderer from './form/FieldRenderer';

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
  const { haptic } = usePlatform();
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

      if (field.type === 'key_value') {
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

  // Listen for external dirty triggers (e.g. child editors)
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
    const secretKeys = new Set(schema.fields.filter(f => f.secret).map(f => f.key));

    for (const [name, value] of formData.entries()) {
      const [, key] = name.split(':', 2);
      if (!key) continue;

      const strValue = String(value).trim();

      if (secretKeys.has(key)) {
        if (strValue === '') {
          if (editingSecrets.has(key)) {
            // Secret field was unlocked and cleared — set to null to trigger deletion
            const parts = key.split('.');
            let target: Record<string, unknown> = payload;
            for (let i = 0; i < parts.length - 1; i++) {
              const part = parts[i]!;
              if (!(part in target)) target[part] = {};
              target = target[part] as Record<string, unknown>;
            }
            target[parts[parts.length - 1]!] = null;
            continue;
          } else {
            // Locked secret input is empty — omit to preserve existing value
            continue;
          }
        }
      }

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
  }, [schema, editingSecrets]);

  async function handleSave() {
    setSaveAttempted(true);

    if (formRef.current) {
      const invalidInput = formRef.current.querySelector('input[data-invalid="true"]');
      if (invalidInput) {
        haptic.notification('error');
        showToast('Fix validation errors before saving', 'error');
        return;
      }

      if (!formRef.current.checkValidity()) {
        formRef.current.reportValidity();
        return;
      }
    }

    const payload = buildPayload();
    setSaving(true);
    const result = await API.saveScope(scope, payload);

    if (result) {
      haptic.notification('success');
      showToast(`${SCOPE_LABELS[scope]} config saved`, 'success');
      setDirty(false);
      setSaveAttempted(false);
      onConfigReload();
    } else {
      haptic.notification('error');
      showToast('Failed to save config', 'error');
    }
    setSaving(false);
  }

  async function handleReload() {
    onConfigReload();
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
    <div class="schema-form-container">
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
          <div class="card" key={groupName}>
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
