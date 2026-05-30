import type { ComponentChildren } from 'preact';
import { Spinner } from './Spinner';

interface ButtonProps {
  /** The content of the button */
  children: ComponentChildren;
  /** Style variant */
  variant?: 'primary' | 'secondary' | 'danger' | 'outline';
  /** Click handler */
  onClick?: () => void;
  /** Shows a loading spinner inside the button */
  loading?: boolean;
  /** Disables the button */
  disabled?: boolean;
  /** Custom CSS classes */
  className?: string;
  /** Custom inline styles */
  style?: Record<string, string | number>;
  /** Unique element identifier */
  id?: string;
}

export function Button({
  children,
  variant = 'primary',
  onClick,
  loading = false,
  disabled = false,
  className = '',
  style,
  id,
}: ButtonProps) {
  let btnStyle: Record<string, string | number> = {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '8px',
    width: '100%',
    minHeight: '46px',
    borderRadius: 'var(--radius-md)',
    fontSize: 'var(--font-size-base)',
    fontWeight: '600',
    border: 'none',
    cursor: disabled || loading ? 'not-allowed' : 'pointer',
    transition: 'transform 0.1s ease, filter 0.15s ease, opacity 0.15s ease',
    outline: 'none',
    boxShadow: '0 2px 4px rgba(0, 0, 0, 0.03)',
    ...style,
  };

  if (variant === 'primary') {
    btnStyle.backgroundColor = 'var(--tg-color-button)';
    btnStyle.color = 'var(--tg-color-button-text)';
  } else if (variant === 'secondary') {
    btnStyle.backgroundColor = 'var(--tg-color-separator)';
    btnStyle.color = 'var(--tg-color-link)';
  } else if (variant === 'danger') {
    btnStyle.backgroundColor = 'rgba(255, 59, 48, 0.1)';
    btnStyle.color = 'var(--tg-color-destructive)';
  } else if (variant === 'outline') {
    btnStyle.backgroundColor = 'transparent';
    btnStyle.border = '1px solid var(--tg-color-divider)';
    btnStyle.color = 'var(--tg-color-text)';
  }

  if (disabled) {
    btnStyle.opacity = 0.55;
    btnStyle.boxShadow = 'none';
  }

  const handleClick = () => {
    if (!disabled && !loading && onClick) {
      onClick();
    }
  };

  return (
    <button
      id={id}
      onClick={handleClick}
      disabled={disabled || loading}
      className={`tg-button tg-button-${variant} ${className}`}
      style={btnStyle}
    >
      {loading && <Spinner size={16} color={variant === 'primary' ? '#ffffff' : 'var(--tg-color-link)'} />}
      {children}
    </button>
  );
}
