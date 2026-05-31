/**
 * App — Root component. Manages config fetching, SSE streaming,
 * and provides stack navigation for MainScreen / BuildDetailScreen.
 */

import { useCallback, useEffect, useRef, useState } from 'preact/hooks';
import { usePlatform } from 'platform-core';
import { useNavigator, Navigator, ErrorBoundary } from 'tg-ui-preact';
import { useSSE } from './hooks/useSSE';
import { fetchConfig, fetchRecentBuilds, ApiError } from './api';
import LoadingScreen from './components/LoadingScreen';
import ErrorScreen from './components/ErrorScreen';
import MainScreen from './components/MainScreen';
import BuildDetailScreen from './components/BuildDetailScreen';
import type { ActiveBuild, AppConfig, ApiErrorDetail } from './types';

interface ErrorState {
  title: string;
  description: string;
  detail: ApiErrorDetail | null;
}

function AppShell() {
  const platform = usePlatform();
  const { initData } = platform;
  const navigator = useNavigator();

  const [config, setConfig] = useState<AppConfig | null>(null);
  const [error, setError] = useState<ErrorState | null>(null);

  // Ref mirrors the navigator's current screen for SSE callback
  // (callbacks close over stale hook state without this).
  const currentRef = useRef(navigator.current);
  currentRef.current = navigator.current;

  // If not in Telegram, block access
  const hasTelegram = platform.initData !== '';

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

    // Auto-transition: if viewing an active build detail and it just
    // completed, fetch recent builds and switch to the result screen.
    const viewing = currentRef.current;
    if (viewing?.type === 'active') {
      const stillActive = builds.some((b) => b.request_id === viewing.id);
      if (!stillActive) {
        fetchRecentBuilds(initData)
          .then((recent) => {
            const match = recent.find((r) => r.request_id === viewing.id);
            if (match) {
              navigator.replace({ screen: 'build-detail', type: 'recent', id: match.request_id });
            } else {
              // Build completed but not yet in recent — return to main
              navigator.pop();
            }
          })
          .catch(() => {
            // Fetch failed — return to main screen gracefully
            navigator.pop();
          });
      }
    }
  }, [initData, navigator]);

  useSSE(sseUrl, handleBuildsUpdate);


  if (error) {
    return (
      <ErrorScreen
        title={error.title}
        description={error.description}
        detail={error.detail}
      />
    );
  }

  if (!config) {
    return <LoadingScreen />;
  }

  return (
    <Navigator
      phase={navigator.phase}
      mainScreen={
        <MainScreen
          config={config}
          onBuildSelect={(type, id) =>
            navigator.push({ screen: 'build-detail', type, id })
          }
        />
      }
      detailScreen={
        navigator.current ? (
          <BuildDetailScreen
            config={config}
            type={navigator.current.type}
            id={navigator.current.id}
            onBack={() => navigator.pop()}
          />
        ) : null
      }
      exitingScreen={
        navigator.exiting ? (
          <BuildDetailScreen
            config={config}
            type={navigator.exiting.type}
            id={navigator.exiting.id}
            onBack={() => navigator.pop()}
          />
        ) : null
      }
    />
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <AppShell />
    </ErrorBoundary>
  );
}
