import type { ComponentChildren } from 'preact';
import { ChevronRight } from 'lucide-preact';

interface ListItemProps {
  /** Core label content */
  title: ComponentChildren;
  /** Sub-label description beneath the title */
  subtitle?: ComponentChildren;
  /** Mono-spaced metadata tag badge below the title */
  meta?: ComponentChildren;
  /** Component on the left (e.g. icon) */
  prefix?: ComponentChildren;
  /** Click action callback */
  onClick?: () => void;
  /** Displays a checkmark icon and highlights selection */
  selected?: boolean;
  /** Custom element on the right (e.g. toggle Switch) */
  rightElement?: ComponentChildren;
  /** Restricts interactions */
  disabled?: boolean;
  /** Custom CSS classes */
  className?: string;
  /** Unique element ID */
  id?: string;
}

export function ListItem({
  title,
  subtitle,
  meta,
  prefix,
  onClick,
  selected = false,
  rightElement,
  disabled = false,
  className = '',
  id,
}: ListItemProps) {
  const itemClass = `tg-list-item ${selected ? 'selected' : ''} ${disabled ? 'disabled' : ''} ${className}`;

  const content = (
    <>
      {prefix && <div className="tg-list-item-prefix" style={{ marginRight: '12px', display: 'flex', alignItems: 'center' }}>{prefix}</div>}
      
      <div className="tg-list-item-content">
        <span className="tg-list-item-title">{title}</span>
        {subtitle && <span className="tg-list-item-subtitle">{subtitle}</span>}
        {meta && <div style={{ marginTop: '4px' }}><span className="tg-list-item-meta">{meta}</span></div>}
      </div>

      {rightElement && <div className="tg-list-item-right" style={{ display: 'flex', alignItems: 'center' }}>{rightElement}</div>}
      
      {selected && (
        <div className="tg-radio-icon">
          <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" strokeWidth="3" fill="none" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12" />
          </svg>
        </div>
      )}

      {onClick && !selected && !rightElement && (
        <ChevronRight size={18} className="tg-color-hint" style={{ opacity: 0.5, flexShrink: 0 }} />
      )}
    </>
  );

  if (onClick && !disabled) {
    return (
      <div className={itemClass} onClick={onClick} id={id}>
        {content}
      </div>
    );
  }

  return (
    <div className={itemClass} id={id}>
      {content}
    </div>
  );
}
