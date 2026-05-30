import { useEffect } from 'preact/hooks';
import { useTelegram } from '../context/TelegramContext';

/**
 * useBackButton — Declarative hook for the Telegram WebApp BackButton.
 *
 * Automatically handles show/hide lifecycle, callback registration, and
 * cleanup on unmount for the singleton BackButton.
 *
 * @param isActive Whether the calling screen is the active (topmost) screen.
 * @param onBack Callback triggered when the BackButton is pressed.
 */
export function useBackButton(isActive: boolean, onBack: () => void) {
  const { isTelegram, tg } = useTelegram();

  useEffect(() => {
    if (!isTelegram || !tg) return;

    if (isActive) {
      tg.BackButton.show();
      tg.BackButton.onClick(onBack);
    } else {
      tg.BackButton.offClick(onBack);
      tg.BackButton.hide();
    }

    return () => {
      tg.BackButton.offClick(onBack);
      tg.BackButton.hide();
    };
  }, [isTelegram, tg, isActive, onBack]);
}
