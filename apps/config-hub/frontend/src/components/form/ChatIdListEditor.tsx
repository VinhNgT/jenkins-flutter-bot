/**
 * ChatIdListEditor — Interactive chat ID list with chip-based display.
 *
 * Renders existing IDs as visual chips (group vs. user). Provides
 * add/delete/copy functionality with inline validation.
 */

import { Check, Copy, Plus, Trash2, User, Users } from 'lucide-preact';
import { useEffect, useRef, useState } from 'preact/hooks';

interface ChatIdItem {
  id: string;
  value: number;
}

interface ChatIdListEditorProps {
  name: string;
  value: string;
}

export default function ChatIdListEditor({ name, value }: ChatIdListEditorProps) {
  const initialItemsRef = useRef<ChatIdItem[]>([]);
  const [items, setItems] = useState<ChatIdItem[]>(() => {
    let initial: ChatIdItem[] = [];
    try {
      const trimmed = (value || '').trim();
      if (trimmed.startsWith('[')) {
        const parsed = JSON.parse(trimmed);
        if (Array.isArray(parsed)) {
          initial = parsed.map(x => ({
            id: Math.random().toString(36).substring(2, 9),
            value: Number(x),
          }));
        }
      } else if (trimmed) {
        initial = trimmed
          .split(',')
          .map(x => x.trim())
          .filter(Boolean)
          .map(x => ({
            id: Math.random().toString(36).substring(2, 9),
            value: Number(x),
          }));
      }
    } catch {
      // Fallback
      if (value) {
        initial = String(value)
          .split(',')
          .map(x => x.trim())
          .filter(Boolean)
          .map(x => ({
            id: Math.random().toString(36).substring(2, 9),
            value: Number(x),
          }));
      }
    }
    initialItemsRef.current = initial;
    return initial;
  });

  const [newValue, setNewValue] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const hiddenInputRef = useRef<HTMLInputElement>(null);

  // Sync state to comma-separated values in hidden input
  useEffect(() => {
    if (hiddenInputRef.current) {
      const serialized = items.map(item => item.value).join(',');
      hiddenInputRef.current.value = serialized;
      hiddenInputRef.current.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }, [items]);

  const handleInputChange = (e: Event) => {
    const val = (e.target as HTMLInputElement).value;
    if (/^-?\d*$/.test(val)) {
      setNewValue(val);
      setError(null);
    }
  };

  const handleAdd = () => {
    const trimmed = newValue.trim();
    if (!trimmed) return;

    const num = Number(trimmed);
    if (isNaN(num) || !/^-?\d+$/.test(trimmed)) {
      setError('⚠️ Invalid Chat ID. Must be a valid integer.');
      return;
    }

    if (items.some(item => item.value === num)) {
      setError('⚠️ This Chat ID is already in the list.');
      return;
    }

    setItems(prev => [
      ...prev,
      {
        id: Math.random().toString(36).substring(2, 9),
        value: num,
      },
    ]);
    setNewValue('');
    setError(null);
  };

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleAdd();
    }
  };

  const handleDelete = (id: string) => {
    setItems(prev => prev.filter(item => item.id !== id));
  };

  const handleCopy = (id: string, val: number) => {
    navigator.clipboard.writeText(String(val)).then(() => {
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 1500);
    });
  };

  return (
    <div class="chat-id-list-editor">
      {items.length === 0 ? (
        <div class="kv-empty-state" style={{ marginBottom: 'var(--space-sm)' }}>
          <p>No Allowed Chat IDs configured. The bot will reject all interactions.</p>
        </div>
      ) : (
        <div class="chat-id-chips">
          {items.map(item => {
            const isGroup = item.value < 0;
            const isCopied = copiedId === item.id;
            
            // Check dirty state
            const initialItem = initialItemsRef.current.find(x => x.value === item.value);
            const isItemDirty = !initialItem;

            return (
              <div 
                class={`chat-id-chip${isItemDirty ? ' chat-id-chip--dirty' : ''}`}
                key={item.id}
              >
                <span class={`chat-id-chip__icon ${isGroup ? 'group' : 'user'}`}>
                  {isGroup ? <Users size={12} /> : <User size={12} />}
                </span>
                <span class="chat-id-chip__value">{item.value}</span>
                <span class={`chat-id-chip__badge ${isGroup ? 'group' : 'user'}`}>
                  {isGroup ? 'Group' : 'User'}
                </span>
                <div class="chat-id-chip__actions">
                  <button
                    type="button"
                    class="btn-chip-action"
                    onClick={() => handleCopy(item.id, item.value)}
                    title="Copy Chat ID"
                  >
                    {isCopied ? <Check size={11} style={{ color: 'var(--tg-color-success)' }} /> : <Copy size={11} />}
                  </button>
                  <button
                    type="button"
                    class="btn-chip-action delete"
                    onClick={() => handleDelete(item.id)}
                    title="Delete Chat ID"
                  >
                    <Trash2 size={11} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div class="chat-id-add-form">
        <input
          type="text"
          class="form-input chat-id-add-input"
          placeholder="Enter Chat ID (e.g. -100123456)"
          value={newValue}
          onInput={handleInputChange}
          onKeyDown={handleKeyDown}
        />
        <button 
          type="button" 
          class="btn btn-sm btn-secondary" 
          onClick={handleAdd}
          disabled={!newValue.trim()}
        >
          <Plus class="icon" size={12} /> Add
        </button>
      </div>

      {error ? (
        <div class="chat-id-validation-error">{error}</div>
      ) : (
        <div class="chat-id-helper-text">
          💡 Group/channel IDs are negative numbers starting with <code>-100</code>. User IDs are positive numbers.
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
