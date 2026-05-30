interface InputProps {
  /** Input value binding state */
  value: string;
  /** Triggered on user typing input */
  onChange: (v: string) => void;
  /** Floating placeholder hint */
  placeholder?: string;
  /** Input type (e.g. 'text', 'password', 'number') */
  type?: string;
  /** Restricts edit access */
  disabled?: boolean;
  /** Displays clear button icon */
  clearable?: boolean;
  /** Custom CSS classes */
  className?: string;
}

export function Input({
  value,
  onChange,
  placeholder = '',
  type = 'text',
  disabled = false,
  clearable = true,
  className = '',
}: InputProps) {
  const isPopulated = value.length > 0;

  const handleClear = (e: MouseEvent) => {
    e.stopPropagation();
    onChange('');
  };

  return (
    <div className={`tg-input-row ${isPopulated ? 'populated' : ''} ${className}`}>
      <input
        type={type}
        value={value}
        onInput={(e) => onChange((e.target as HTMLInputElement).value)}
        placeholder={placeholder}
        disabled={disabled}
        className="tg-input-field"
      />
      {clearable && !disabled && (
        <span onClick={handleClear} className="tg-input-clear">
          ✕
        </span>
      )}
    </div>
  );
}
