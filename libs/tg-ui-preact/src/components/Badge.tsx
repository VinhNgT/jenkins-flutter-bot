import type { ComponentChildren } from 'preact';

export interface BadgeProps {
  /** Content of the badge */
  children: ComponentChildren;
  /** Semantic color variant themes */
  variant?: 'success' | 'danger' | 'warning' | 'info' | 'neutral';
  /** Legacy type property, mapped internally to variant */
  type?: 'success' | 'failure' | 'timeout' | 'cancelled' | 'warning' | 'info';
  /** Custom CSS classes */
  className?: string;
}

export function Badge({
  children,
  variant,
  type,
  className = '',
}: BadgeProps) {
  // Map legacy types to generic variants if variant is not explicitly provided
  const activeVariant = variant ?? (
    type === 'failure' ? 'danger' :
    type === 'timeout' ? 'warning' :
    type === 'cancelled' ? 'neutral' :
    type
  ) ?? 'info';

  return (
    <span className={`tg-result-badge ${activeVariant} ${className}`}>
      {children}
    </span>
  );
}

