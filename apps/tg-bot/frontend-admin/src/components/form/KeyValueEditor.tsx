/**
 * KeyValueEditor — Interactive key-value pair editor.
 *
 * Used for build options (display label → git branch). Serializes rows
 * to a JSON object in a hidden input, with validation for incomplete
 * or duplicate keys.
 */

import { Plus, Trash2 } from 'lucide-preact';
import { useEffect, useRef, useState } from 'preact/hooks';

interface KeyValueRow {
  id: string;
  key: string;
  value: string;
}

interface KeyValueEditorProps {
  name: string;
  value: string;
}

export default function KeyValueEditor({ name, value }: KeyValueEditorProps) {
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
                  class={`form-input kv-input-key${isKeyDirty ? ' kv-input--dirty' : ''}`}
                  placeholder="Display Label (e.g. Stable Release)"
                  value={row.key}
                  onInput={(e) => updateRow(row.id, 'key', (e.target as HTMLInputElement).value)}
                />
                <span class="kv-arrow">➔</span>
                <input
                  type="text"
                  class={`form-input kv-input-value${isValueDirty ? ' kv-input--dirty' : ''}`}
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
