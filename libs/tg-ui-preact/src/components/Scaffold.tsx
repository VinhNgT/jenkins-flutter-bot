import type { ComponentChildren } from 'preact';
import { useContext, useEffect } from 'preact/hooks';
import { ChevronLeft } from 'lucide-preact';
import { BackButtonContext } from '../context/BackButtonContext';
import { useScreenActive } from '../context/ScreenActiveContext';

export interface ScaffoldProps {
  /** Page header title (optional) */
  title?: string;
  /** Subtitle or description under the title (optional) */
  subtitle?: string;
  /** Callback for visual back button navigation. If omitted, no back button is rendered. */
  onBack?: () => void;
  /** Optional right-side header controls / actions */
  headerActions?: ComponentChildren;
  /** Main page content */
  children: ComponentChildren;
}

export function Scaffold({
  title,
  subtitle,
  onBack,
  headerActions,
  children,
}: ScaffoldProps) {
  const registry = useContext(BackButtonContext);
  const isActive = useScreenActive();

  // Automatically register the back button callback with the platform context if available
  useEffect(() => {
    if (!onBack || !registry || !isActive) return;
    const unregister = registry.register(onBack);
    return unregister;
  }, [onBack, registry, isActive]);

  // Visual back button is shown if onBack is provided AND the active provider has no physical button support
  const showVisualBackButton = onBack && (!registry || !registry.hasPhysicalBackButton);

  return (
    <div className="container" style={{ display: 'flex', flexDirection: 'column', minHeight: '100%' }}>
      {showVisualBackButton && (
        <header style={{ display: 'flex', alignItems: 'center', width: '100%' }}>
          <button className="back-button" onClick={onBack}>
            <ChevronLeft size={20} />
            <span>Back</span>
          </button>
        </header>
      )}

      {(title || subtitle || headerActions) && (
        <div
          className="scaffold-header"
          style={{
            marginBottom: 'var(--space-md)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            width: '100%',
          }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0, flex: 1 }}>
            {title && <h2 className="panel-title" style={{ margin: 0 }}>{title}</h2>}
            {subtitle && <p className="panel-desc" style={{ marginTop: 'var(--space-xs)', marginBottom: 0 }}>{subtitle}</p>}
          </div>
          {headerActions && (
            <div className="header-actions" style={{ flexShrink: 0, marginLeft: 'var(--space-md)' }}>
              {headerActions}
            </div>
          )}
        </div>
      )}

      <div className="scaffold-content" style={{ flex: 1, display: 'flex', flexDirection: 'column', width: '100%' }}>
        {children}
      </div>
    </div>
  );
}
