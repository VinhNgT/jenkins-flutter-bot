import { useEffect, useState } from 'preact/hooks';

export function useTheme(): {
  colorScheme: 'light' | 'dark';
  isDark: boolean;
} {
  const tg = typeof window !== 'undefined' ? window.Telegram?.WebApp : null;
  const [scheme, setScheme] = useState<'light' | 'dark'>(tg?.colorScheme ?? 'light');

  useEffect(() => {
    if (!tg) return;
    const handleThemeChange = () => {
      setScheme(tg.colorScheme);
    };
    tg.onEvent('themeChanged', handleThemeChange);
    return () => {
      tg.offEvent('themeChanged', handleThemeChange);
    };
  }, [tg]);

  return {
    colorScheme: scheme,
    isDark: scheme === 'dark',
  };
}
