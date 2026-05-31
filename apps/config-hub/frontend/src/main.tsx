import { render } from 'preact';
import './styles/global.css';
import App from './App';
import { ToastProvider } from './context/ToastContext';
import { ConfirmProvider } from './context/ConfirmDialog';
import { TelegramProvider } from 'tg-core-preact';
import { BrowserPlatformProvider, usePlatform } from 'platform-core';
import { ThemeProvider, BackButtonContext, ErrorBoundary } from 'tg-ui-preact';

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
  const isTelegram = typeof window !== 'undefined' && !!window.Telegram?.WebApp;
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
