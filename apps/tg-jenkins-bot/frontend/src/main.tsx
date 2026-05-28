/**
 * Entry point — Mounts the Preact app into #app.
 *
 * Wraps in TelegramProvider and ToastProvider contexts.
 * Loads the emulator in development mode before rendering.
 */

import { render } from 'preact';
import { TelegramProvider } from './context/TelegramContext';
import { ToastProvider } from './context/ToastContext';
import App from './App';
import './styles/global.css';

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
    <TelegramProvider>
      <ToastProvider>
        <App />
      </ToastProvider>
    </TelegramProvider>,
    document.getElementById('app')!,
  );
}

bootstrap();
