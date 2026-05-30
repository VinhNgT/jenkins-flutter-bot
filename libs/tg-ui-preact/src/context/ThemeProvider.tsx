import type { ComponentChildren } from 'preact';
import { useEffect } from 'preact/hooks';

export interface ThemeTokens {
  bg_color?: string;
  secondary_bg_color?: string;
  text_color?: string;
  hint_color?: string;
  link_color?: string;
  button_color?: string;
  button_text_color?: string;
  destructive_text_color?: string;
  section_bg_color?: string;
  section_header_text_color?: string;
  subtitle_text_color?: string;
  header_bg_color?: string;
  section_separator_color?: string;
  bottom_bar_bg_color?: string;
}

export interface ThemeProviderProps {
  theme?: ThemeTokens;
  isDark?: boolean;
  children: ComponentChildren;
}

export function ThemeProvider({ theme = {}, isDark = false, children }: ThemeProviderProps) {
  useEffect(() => {
    const root = document.documentElement;

    // Toggle body theme classes
    document.body.classList.toggle('tg-dark', isDark);
    document.body.classList.toggle('tg-light', !isDark);
    document.body.classList.add('tg-theme-loaded');
    root.classList.add('tg-theme-loaded');

    // Map theme tokens to CSS custom properties
    if (theme.bg_color) root.style.setProperty('--tg-color-bg', theme.bg_color);
    if (theme.secondary_bg_color) root.style.setProperty('--tg-color-secondary-bg', theme.secondary_bg_color);
    if (theme.text_color) root.style.setProperty('--tg-color-text', theme.text_color);
    if (theme.hint_color) root.style.setProperty('--tg-color-hint', theme.hint_color);
    if (theme.link_color) root.style.setProperty('--tg-color-link', theme.link_color);
    if (theme.button_color) root.style.setProperty('--tg-color-button', theme.button_color);
    if (theme.button_text_color) root.style.setProperty('--tg-color-button-text', theme.button_text_color);
    if (theme.destructive_text_color) root.style.setProperty('--tg-color-destructive', theme.destructive_text_color);

    // Section colors (API 7.0+)
    root.style.setProperty('--tg-color-section-bg', theme.section_bg_color ?? theme.bg_color ?? (isDark ? '#1c242c' : '#ffffff'));
    root.style.setProperty('--tg-color-section-header', theme.section_header_text_color ?? theme.hint_color ?? (isDark ? '#708499' : '#8e8e93'));
    root.style.setProperty('--tg-color-subtitle', theme.subtitle_text_color ?? theme.hint_color ?? (isDark ? '#708499' : '#8e8e93'));
    root.style.setProperty('--tg-color-header-bg', theme.header_bg_color ?? theme.secondary_bg_color ?? (isDark ? '#0f171e' : '#f4f4f7'));

    // API 7.6 Section separator
    const separatorColor = theme.section_separator_color ?? (isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.08)');
    root.style.setProperty('--tg-color-separator', separatorColor);
    root.style.setProperty('--tg-color-divider', separatorColor);
  }, [theme, isDark]);

  return <>{children}</>;
}
