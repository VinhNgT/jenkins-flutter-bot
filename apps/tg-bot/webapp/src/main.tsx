/**
 * Entry point — Mounts the Preact app into #app.
 *
 * Wraps in the active PlatformProvider (core logic) and bridges theme
 * and back-button registry states to ThemeProvider/BackButtonContext (visuals).
 */

import { render } from 'preact';
import { TelegramProvider } from 'tg-core-preact';
import { BrowserPlatformProvider, usePlatform } from 'platform-core';
import { ThemeProvider, BackButtonContext } from 'tg-ui-preact';
import { ToastProvider } from './context/ToastContext';
import App from './App';
import './styles/global.css';

function AppBootstrap() {
  const platform = usePlatform();
  const tg = typeof window !== 'undefined' ? window.Telegram?.WebApp : null;

  const isDark = tg?.colorScheme === 'dark';
  const theme = tg?.themeParams ?? {};

  // Map visual Scaffold back-button registrations to the native platform's BackButton API
  const backButtonRegistry = {
    hasPhysicalBackButton: platform.hasPhysicalBackButton,
    register: (onClick: () => void) => {
      if (!platform.hasPhysicalBackButton) return () => {};
      const tgApp = window.Telegram?.WebApp;
      if (!tgApp) return () => {};
      const btn = tgApp.BackButton;
      btn.onClick(onClick);
      btn.show();
      return () => {
        btn.offClick(onClick);
        btn.hide();
      };
    }
  };

  return (
    <BackButtonContext.Provider value={backButtonRegistry}>
      <ThemeProvider theme={theme} isDark={isDark}>
        <App />
      </ThemeProvider>
    </BackButtonContext.Provider>
  );
}

function bootstrap() {
  const isTelegram = typeof window !== 'undefined' && !!window.Telegram?.WebApp?.initData;
  const Provider = isTelegram ? TelegramProvider : BrowserPlatformProvider;

  render(
    <Provider>
      <ToastProvider>
        <AppBootstrap />
      </ToastProvider>
    </Provider>,
    document.getElementById('app')!,
  );
}

bootstrap();
