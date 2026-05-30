interface TextAreaProps {
  /** Textarea value binding state */
  value: string;
  /** Triggered on user typing */
  onChange?: (v: string) => void;
  /** Placeholder hint */
  placeholder?: string;
  /** Vertical row count */
  rows?: number;
  /** Restricts edit access */
  disabled?: boolean;
  /** Restricts editing but allows copying */
  readOnly?: boolean;
  /** Custom CSS classes */
  className?: string;
  /** Custom inline styles */
  style?: Record<string, string | number>;
}

export function TextArea({
  value,
  onChange,
  placeholder = '',
  rows = 3,
  disabled = false,
  readOnly = false,
  className = '',
  style,
}: TextAreaProps) {
  const handleInput = (e: Event) => {
    if (onChange) {
      onChange((e.target as HTMLTextAreaElement).value);
    }
  };

  return (
    <div className={`tg-input-row ${className}`} style={{ minHeight: 'auto', alignItems: 'stretch' }}>
      <textarea
        value={value}
        onInput={handleInput}
        placeholder={placeholder}
        rows={rows}
        disabled={disabled}
        readOnly={readOnly}
        className="tg-input-field"
        style={{ resize: 'none', width: '100%', padding: '12px 0', ...style }}
      />
    </div>
  );
}
