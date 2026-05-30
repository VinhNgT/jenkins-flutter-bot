import { render } from 'preact';
import './styles/global.css';
import App from './App';
import ErrorBoundary from './components/ErrorBoundary';
import { ToastProvider } from './context/ToastContext';
import { ConfirmProvider } from './context/ConfirmDialog';
import { TelegramProvider } from './context/TelegramContext';

// Conditionally load the Telegram SDK emulator in dev mode.
// The emulator injects window.Telegram.WebApp on localhost
// when no real SDK is present. It must run before App mounts
// so TelegramProvider sees the mock SDK.
async function bootstrap() {
  const isLocalHost = ['localhost', '127.0.0.1'].includes(location.hostname);
  const hasRealSDK = !!window.Telegram?.WebApp?.initData;

  if (isLocalHost && !hasRealSDK) {
    await import('./emulator');
  }

  render(
    <ErrorBoundary>
      <TelegramProvider>
        <ToastProvider>
          <ConfirmProvider>
            <App />
          </ConfirmProvider>
        </ToastProvider>
      </TelegramProvider>
    </ErrorBoundary>,
    document.getElementById('app')!,
  );
}

bootstrap();

