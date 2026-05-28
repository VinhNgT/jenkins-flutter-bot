/**
 * useMainButton — Declarative hook for Telegram tg.MainButton.
 *
 * Replaces scattered imperative tg.MainButton.* calls with a single
 * declarative interface. Each screen describes the desired button state;
 * the hook handles applying params, registering/unregistering click
 * handlers, managing progress spinner, and full cleanup on unmount
 * or deactivation.
 *
 * The `isActive` flag resolves the singleton contention problem: when
 * multiple screens are mounted simultaneously (overlay pattern), only
 * the topmost screen's hook instance controls the physical button.
 * Inactive instances skip all operations and fully reset on deactivation.
 */

import { useEffect, useRef } from 'preact/hooks';
import { useTelegram } from '../context/TelegramContext';

export interface MainButtonConfig {
  /** Button label text (e.g. "TRIGGER BUILD", "CANCEL BUILD") */
  text: string;
  /** Background color (defaults to theme button_color) */
  color?: string;
  /** Text color (defaults to theme button_text_color) */
  textColor?: string;
  /** Whether to show the loading spinner */
  loading?: boolean;
  /** Whether the button is disabled (visible but non-interactive) */
  disabled?: boolean;
  /** Click handler — stable reference recommended (useCallback) */
  onClick: () => void;
}

/**
 * Declaratively manage tg.MainButton lifecycle.
 *
 * @param config - Desired button state, or `null` to hide the button.
 * @param isActive - Whether this screen is the topmost (owns the button).
 *                   When false, the hook yields control and fully resets.
 */
export function useMainButton(
  config: MainButtonConfig | null,
  isActive: boolean,
): void {
  const { tg, isTelegram } = useTelegram();
  const onClickRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (!isTelegram || !tg) return;

    // When not active or no config, fully reset and yield control
    if (!isActive || !config) {
      // Remove any previously registered handler
      if (onClickRef.current) {
        tg.MainButton.offClick(onClickRef.current);
        onClickRef.current = null;
      }
      tg.MainButton.hideProgress();
      tg.MainButton.hide();
      return;
    }

    // Apply desired state
    const color = config.color ?? tg.themeParams.button_color ?? '#2481cc';
    const textColor = config.textColor ?? tg.themeParams.button_text_color ?? '#ffffff';

    tg.MainButton.setParams({
      text: config.text,
      color,
      text_color: textColor,
      is_active: !config.disabled,
      is_visible: true,
    });

    // Sync progress spinner
    if (config.loading) {
      tg.MainButton.showProgress(false);
      tg.MainButton.disable();
    } else {
      tg.MainButton.hideProgress();
      if (!config.disabled) {
        tg.MainButton.enable();
      }
    }

    // Swap click handler if it changed
    if (onClickRef.current !== config.onClick) {
      if (onClickRef.current) {
        tg.MainButton.offClick(onClickRef.current);
      }
      tg.MainButton.onClick(config.onClick);
      onClickRef.current = config.onClick;
    }

    // Full cleanup on unmount or dependency change
    return () => {
      if (onClickRef.current) {
        tg.MainButton.offClick(onClickRef.current);
        onClickRef.current = null;
      }
      tg.MainButton.hideProgress();
      tg.MainButton.hide();
    };
  }, [isTelegram, tg, isActive, config?.text, config?.color, config?.textColor,
      config?.loading, config?.disabled, config?.onClick]);
}
