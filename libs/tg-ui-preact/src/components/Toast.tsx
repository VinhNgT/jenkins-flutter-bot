import type { ComponentChildren } from 'preact';

interface ToastProps {
  /** The message text to display */
  message: string;
  /** Active display status state */
  active: boolean;
  /** Semantic context type */
  type?: 'success' | 'error';
  /** Optional icon prefix element */
  icon?: ComponentChildren;
  /** Custom CSS classes */
  className?: string;
}

export function Toast({
  message,
  active,
  type = 'success',
  icon,
  className = '',
}: ToastProps) {
  return (
    <div
      className={`tg-toast ${active ? 'active' : ''} ${type === 'error' ? 'toast-error' : ''} ${className}`}
    >
      {icon && <div className="tg-toast-icon">{icon}</div>}
      <span>{message}</span>
    </div>
  );
}
