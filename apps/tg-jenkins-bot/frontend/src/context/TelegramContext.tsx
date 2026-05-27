/**
 * TelegramContext — Provides typed access to the Telegram Web App SDK.
 *
 * Initializes the SDK once on mount, syncs theme CSS variables,
 * and loads the emulator in development mode.
 */

import { createContext } from 'preact';
import { useContext, useEffect, useMemo, useRef } from 'preact/hooks';
import type { ComponentChildren } from 'preact';

interface TelegramContextValue {
  tg: TelegramWebApp | null;
  isTelegram: boolean;
  initData: string;
  userId: number | null;
  haptic: {
    tap(): void;
    impact(style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft'): void;
    notification(type: 'error' | 'success' | 'warning'): void;
  };
}

const TelegramContext = createContext<TelegramContextValue | null>(null);

/** Sync Telegram theme params into CSS custom properties on :root. */
function syncThemeColors(tg: TelegramWebApp): void {
  const theme = tg.themeParams;
  const isDark = tg.colorScheme === 'dark';
  const root = document.documentElement;

  // Toggle body theme classes
  document.body.classList.toggle('tg-dark', isDark);
  document.body.classList.toggle('tg-light', !isDark);
  document.body.classList.add('tg-theme-loaded');
  root.classList.add('tg-theme-loaded');

  // Map SDK theme params to our CSS custom properties
  if (theme.bg_color) root.style.setProperty('--tg-color-bg', theme.bg_color);
  if (theme.secondary_bg_color) root.style.setProperty('--tg-color-secondary-bg', theme.secondary_bg_color);
  if (theme.text_color) root.style.setProperty('--tg-color-text', theme.text_color);
  if (theme.hint_color) root.style.setProperty('--tg-color-hint', theme.hint_color);
  if (theme.link_color) root.style.setProperty('--tg-color-link', theme.link_color);
  if (theme.button_color) root.style.setProperty('--tg-color-button', theme.button_color);
  if (theme.button_text_color) root.style.setProperty('--tg-color-button-text', theme.button_text_color);
  if (theme.destructive_text_color) root.style.setProperty('--tg-color-destructive', theme.destructive_text_color);

  // API 7.0+ section-level params
  root.style.setProperty('--tg-color-section-bg', theme.section_bg_color ?? theme.bg_color ?? (isDark ? '#1c242c' : '#ffffff'));
  root.style.setProperty('--tg-color-section-header', theme.section_header_text_color ?? theme.hint_color ?? (isDark ? '#708499' : '#8e8e93'));
  root.style.setProperty('--tg-color-subtitle', theme.subtitle_text_color ?? theme.hint_color ?? (isDark ? '#708499' : '#8e8e93'));
  root.style.setProperty('--tg-color-header-bg', theme.header_bg_color ?? theme.secondary_bg_color ?? (isDark ? '#0f171e' : '#f4f4f7'));

  // API 7.6: section separator
  const separatorColor = theme.section_separator_color ?? (isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.08)');
  root.style.setProperty('--tg-color-separator', separatorColor);
  root.style.setProperty('--tg-color-divider', separatorColor);

  // Native header colors
  tg.setHeaderColor('secondary_bg_color');
  tg.setBackgroundColor('secondary_bg_color');
}

export function TelegramProvider({ children }: { children: ComponentChildren }) {
  const initializedRef = useRef(false);

  const value = useMemo<TelegramContextValue>(() => {
    const tg = window.Telegram?.WebApp ?? null;
    const isTelegram = !!(tg && tg.initData && tg.initData !== 'preview');
    const initData = tg?.initData ?? 'preview';
    const userId = tg?.initDataUnsafe?.user?.id ?? null;

    const haptic = {
      tap() {
        // Disabled: Haptics reserved for important actions/events only
      },
      impact(style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft') {
        try { if (isTelegram) tg!.HapticFeedback.impactOccurred(style); } catch { /* noop */ }
      },
      notification(type: 'error' | 'success' | 'warning') {
        try { if (isTelegram) tg!.HapticFeedback.notificationOccurred(type); } catch { /* noop */ }
      },
    };

    return { tg, isTelegram, initData, userId, haptic };
  }, []);

  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;

    const { tg, isTelegram } = value;

    if (tg && isTelegram) {
      // Full SDK initialization
      tg.ready();
      tg.expand();
      tg.disableVerticalSwipes?.();
      if (tg.setBottomBarColor) tg.setBottomBarColor('secondary_bg_color');

      // Initial theme sync + listen for changes
      syncThemeColors(tg);
      tg.onEvent('themeChanged', () => syncThemeColors(tg));
    } else if (tg && tg.initData === 'preview') {
      // Emulator mode — SDK was loaded by emulator.ts, sync theme
      syncThemeColors(tg);
      tg.onEvent('themeChanged', () => syncThemeColors(tg));
    }
  }, [value]);

  return (
    <TelegramContext.Provider value={value}>
      {children}
    </TelegramContext.Provider>
  );
}

export function useTelegram(): TelegramContextValue {
  const ctx = useContext(TelegramContext);
  if (!ctx) throw new Error('useTelegram must be used within TelegramProvider');
  return ctx;
}
