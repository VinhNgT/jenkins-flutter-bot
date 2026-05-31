import { render } from 'preact';
import './styles/global.css';
import App from './App';
import { ToastProvider } from './context/ToastContext';
import { ConfirmProvider } from './context/ConfirmDialog';
import { TelegramProvider } from 'tg-core-preact';
import { BrowserPlatformProvider, usePlatform } from 'platform-core';
import { ThemeProvider, BackButtonContext, ErrorBoundary } from 'tg-ui-preact';

import { createAPI } from './api';
import { ApiProvider } from './context/ApiContext';

function AppBootstrap() {
  const platform = usePlatform();
  const api = createAPI(platform.initData);
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
    <ApiProvider api={api}>
      <BackButtonContext.Provider value={backButtonRegistry}>
        <ThemeProvider theme={theme} isDark={isDark}>
          <App />
        </ThemeProvider>
      </BackButtonContext.Provider>
    </ApiProvider>
  );
}

function bootstrap() {
  const isTelegram = typeof window !== 'undefined' && !!window.Telegram?.WebApp?.initData;
  const Provider = isTelegram ? TelegramProvider : BrowserPlatformProvider;

  render(
    <ErrorBoundary>
      <Provider>
        <ToastProvider>
          <ConfirmProvider>
            <AppBootstrap />
          </ConfirmProvider>
        </ToastProvider>
      </Provider>
    </ErrorBoundary>,
    document.getElementById('app')!,
  );
}

bootstrap();
