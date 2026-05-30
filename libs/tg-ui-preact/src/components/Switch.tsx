interface SwitchProps {
  /** Checked status state */
  checked: boolean;
  /** Triggered when toggled */
  onChange: (checked: boolean) => void;
  /** Disables toggle interactions */
  disabled?: boolean;
  /** Custom CSS classes */
  className?: string;
}

export function Switch({
  checked,
  onChange,
  disabled = false,
  className = '',
}: SwitchProps) {
  const toggle = (e: MouseEvent) => {
    e.stopPropagation();
    if (!disabled) {
      onChange(!checked);
    }
  };

  return (
    <div
      onClick={toggle}
      className={`tg-switch ${checked ? 'checked' : ''} ${disabled ? 'disabled' : ''} ${className}`}
      style={{
        width: '40px',
        height: '22px',
        borderRadius: '11px',
        backgroundColor: checked ? 'var(--tg-color-link)' : 'var(--tg-color-separator)',
        position: 'relative',
        cursor: disabled ? 'not-allowed' : 'pointer',
        transition: 'background-color 0.18s ease',
        display: 'flex',
        alignItems: 'center',
        opacity: disabled ? 0.5 : 1,
      }}
    >
      <div
        className="tg-switch-thumb"
        style={{
          width: '18px',
          height: '18px',
          borderRadius: '50%',
          backgroundColor: '#ffffff',
          position: 'absolute',
          left: checked ? '20px' : '2px',
          boxShadow: '0 1px 2px rgba(0,0,0,0.15)',
          transition: 'left 0.18s cubic-bezier(0.25, 0.8, 0.25, 1)',
        }}
      />
    </div>
  );
}
