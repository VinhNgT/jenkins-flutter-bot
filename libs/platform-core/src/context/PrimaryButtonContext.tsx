import { createContext } from 'preact';
import { useContext, useEffect, useRef } from 'preact/hooks';

export interface PrimaryButtonConfig {
  text: string;
  color?: string;
  textColor?: string;
  loading?: boolean;
  disabled?: boolean;
  onClick: () => void;
}

export interface PrimaryButtonRegistry {
  show(config: PrimaryButtonConfig): void;
  hide(): void;
}

export const PrimaryButtonContext = createContext<PrimaryButtonRegistry | null>(null);

/**
 * Declaratively manage a platform's physical or visual primary action button.
 */
export function usePrimaryButton(
  config: PrimaryButtonConfig | null,
  isActive: boolean,
): void {
  const registry = useContext(PrimaryButtonContext);
  const onClickRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (!registry) return;

    if (!isActive || !config) {
      if (onClickRef.current) {
        onClickRef.current = null;
      }
      registry.hide();
      return;
    }

    registry.show(config);
    onClickRef.current = config.onClick;

    return () => {
      if (onClickRef.current) {
        onClickRef.current = null;
      }
      registry.hide();
    };
  }, [registry, isActive, config?.text, config?.color, config?.textColor,
      config?.loading, config?.disabled, config?.onClick]);
}
