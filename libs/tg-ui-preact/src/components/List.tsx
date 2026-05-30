import type { ComponentChildren } from 'preact';

export interface ListProps {
  /** Optional Section header text or custom node */
  header?: ComponentChildren;
  /** Optional Section footer helper text or custom node */
  footer?: ComponentChildren;
  /** List contents (typically ListItems) */
  children: ComponentChildren;
  /** Optional custom styling classes */
  className?: string;
  /** Optional unique element ID */
  id?: string;
}

export function List({ header, footer, children, className = '', id }: ListProps) {
  return (
    <div className={`tg-section ${className}`} id={id}>
      {header && <h3 className="tg-section-header">{header}</h3>}
      <div className="tg-list">
        {children}
      </div>
      {footer && <p className="tg-section-footer">{footer}</p>}
    </div>
  );
}
