/**
 * FieldRenderer — Renders a single configuration field.
 *
 * Dispatches to the appropriate input type based on field metadata:
 * text, number, select, boolean switch, secret, key-value editor,
 * or chat ID list editor. Includes help popover and dirty indicators.
 */

import { useEffect, useRef, useState } from 'preact/hooks';
import type { SchemaField, Scope } from '../../types';
import KeyValueEditor from './KeyValueEditor';
import ChatIdListEditor from './ChatIdListEditor';

interface FieldRendererProps {
  scope: Scope;
  field: SchemaField;
  value: string;
  secretSet: boolean;
  editing: boolean;
  onToggleEdit: () => void;
  isDirty: boolean;
}

export default function FieldRenderer({
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
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!helpOpen) return;

    function handleClickOutside(event: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setHelpOpen(false);
      }
    }

    document.addEventListener('click', handleClickOutside);
    return () => {
      document.removeEventListener('click', handleClickOutside);
    };
  }, [helpOpen]);

  const isSecretLocked = field.secret && secretSet && !editing;

  // For boolean switch fields
  const isBoolean = field.type === 'boolean';

  const getPlaceholder = () => {
    if (field.default !== undefined && field.default !== null && String(field.default) !== '') {
      return String(field.default);
    }
    if (field.placeholder) {
      return field.placeholder;
    }
    if (!field.required) {
      return '(optional)';
    }
    return '';
  };
  
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

  // ─── Label with optional help button ─────────────────────────
  const labelRow = (
    <>
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
    </>
  );

  const helpPopover = field.help_html ? (
    <div class={`field-help-popover-wrapper${helpOpen ? ' visible' : ''}`}>
      <div class="field-help-popover-content">
        <div
          class="field-help-popover"
          dangerouslySetInnerHTML={{ __html: field.help_html }}
        />
      </div>
    </div>
  ) : null;

  const descriptionElement = field.description ? (
    <p class="field-desc">{field.description}</p>
  ) : null;

  // ─── Chat ID List ────────────────────────────────────────────
  if (field.type === 'chat_id_list') {
    return (
      <div
        ref={containerRef}
        class={`field field--chat-id-list field--full${isDirty ? ' field--dirty' : ''}`}
      >
        {labelRow}
        {helpPopover}
        {descriptionElement}
        <ChatIdListEditor name={name} value={value} />
      </div>
    );
  }

  // ─── Key-Value Editor ────────────────────────────────────────
  if (field.type === 'key_value') {
    return (
      <div
        ref={containerRef}
        class={`field field--key-value field--full${isDirty ? ' field--dirty' : ''}`}
      >
        {labelRow}
        {helpPopover}
        {descriptionElement}
        <KeyValueEditor name={name} value={value} />
      </div>
    );
  }

  // ─── Boolean Switch ──────────────────────────────────────────
  if (isBoolean) {
    return (
      <div
        ref={containerRef}
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
            {helpPopover}
            {descriptionElement}
          </div>

          <div class={`tg-toggle-track${checked ? ' tg-toggle-on' : ''}`}>
            <div class="tg-toggle-thumb" />
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

  // ─── Standard Fields (text, number, select, secret) ──────────
  return (
    <div
      ref={containerRef}
      class={`field${field.secret ? ' field--secret' : ''}${field.full_width ? ' field--full' : ''}${isDirty ? ' field--dirty' : ''}`}
    >
      {labelRow}
      {helpPopover}
      {descriptionElement}

      {/* Input */}
      {field.secret ? (
        <div class="secret-row">
          <input
            type="password"
            class="form-input secret"
            name={name}
            autocomplete="off"
            disabled={isSecretLocked}
            required={field.required && !isSecretLocked}
            placeholder={
              isSecretLocked
                ? `••••••••  (${secretSet ? 'set' : 'not set'})`
                : getPlaceholder()
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
          const defaultValue = (() => {
            if (value !== '') {
              return field.options.find((opt) => opt.toLowerCase() === value.toLowerCase()) ?? value;
            }
            if (field.default !== undefined && field.default !== null && String(field.default) !== '') {
              const defStr = String(field.default);
              return field.options.find((opt) => opt.toLowerCase() === defStr.toLowerCase()) ?? defStr;
            }
            return '';
          })();
          return (
            <select class="form-select" name={name} defaultValue={defaultValue} required={field.required}>
              {field.options.map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>
          );
        })()
      ) : (
        <input
          class="form-input"
          name={name}
          type={field.type === 'integer' ? 'number' : 'text'}
          min={field.type === 'integer' ? '0' : undefined}
          defaultValue={value}
          required={field.required}
          placeholder={getPlaceholder()}
        />
      )}
    </div>
  );
}
