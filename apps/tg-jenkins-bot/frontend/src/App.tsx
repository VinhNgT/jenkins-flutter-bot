/**
 * App — Root component. Manages config fetching, SSE streaming,
 * and routes between LoadingScreen, ErrorScreen, and MainScreen.
 */

import { useCallback, useEffect, useState } from 'preact/hooks';
import { useTelegram } from './context/TelegramContext';
import { useSSE } from './hooks/useSSE';
import { fetchConfig, ApiError } from './api';
import ErrorBoundary from './components/ErrorBoundary';
import LoadingScreen from './components/LoadingScreen';
import ErrorScreen from './components/ErrorScreen';
import MainScreen from './components/MainScreen';
import type { ActiveBuild, AppConfig, ApiErrorDetail } from './types';

interface ErrorState {
  title: string;
  description: string;
  detail: ApiErrorDetail | null;
}

export default function App() {
  const { initData, isTelegram, tg } = useTelegram();

  const [config, setConfig] = useState<AppConfig | null>(null);
  const [error, setError] = useState<ErrorState | null>(null);

  // If not in Telegram and not in preview mode, block access
  const hasTelegram = isTelegram || initData === 'preview';

  // Fetch initial config
  useEffect(() => {
    if (!hasTelegram) {
      setError({
        title: 'Telegram Client Required',
        description: 'This application can only be accessed securely inside the official Telegram client messenger.',
        detail: { error: 'direct_browser_disabled' },
      });
      return;
    }

    fetchConfig(initData)
      .then((cfg) => {
        setConfig(cfg);
        setError(null);
      })
      .catch((err) => {
        console.error(err);
        if (err instanceof ApiError) {
          const detail = typeof err.detail === 'object' ? err.detail : null;
          setError({
            title: err.status === 403 || err.status === 401 ? 'Access Denied' : 'Service Offline',
            description: err.message,
            detail,
          });
        } else {
          setError({
            title: 'Service Offline',
            description: 'The build orchestration controller is currently offline or unreachable. Please try again shortly.',
            detail: { error: 'service_offline' },
          });
        }
      });
  }, [initData, hasTelegram]);

  // SSE stream for active builds — only when config is loaded
  const sseUrl = config ? `/api/webapp/stream?init_data=${encodeURIComponent(initData)}` : null;

  const handleBuildsUpdate = useCallback((builds: ActiveBuild[]) => {
    setConfig((prev) => {
      if (!prev) return prev;
      // Skip re-render if builds haven't changed
      if (JSON.stringify(prev.active_builds) === JSON.stringify(builds)) return prev;
      return { ...prev, active_builds: builds };
    });
  }, []);

  useSSE(sseUrl, handleBuildsUpdate);

  // BackButton handler for retrying from error screen
  useEffect(() => {
    if (!isTelegram || !tg) return;

    const handleBack = () => {
      setError(null);
      setConfig(null);
      if (tg.BackButton) tg.BackButton.hide();
      // Refetch config
      fetchConfig(initData)
        .then((cfg) => {
          setConfig(cfg);
          setError(null);
        })
        .catch((err) => {
          console.error(err);
          setError({
            title: 'Service Offline',
            description: 'The build orchestration controller is currently offline or unreachable.',
            detail: { error: 'service_offline' },
          });
        });
    };

    tg.BackButton.onClick(handleBack);
  }, [isTelegram, tg, initData]);

  // Show BackButton when in error state
  useEffect(() => {
    if (!isTelegram || !tg) return;
    if (error) {
      tg.BackButton.show();
    } else {
      tg.BackButton.hide();
    }
  }, [error, isTelegram, tg]);

  return (
    <ErrorBoundary>
      {error ? (
        <ErrorScreen
          title={error.title}
          description={error.description}
          detail={error.detail}
        />
      ) : config ? (
        <MainScreen config={config} />
      ) : (
        <LoadingScreen />
      )}
    </ErrorBoundary>
  );
}
