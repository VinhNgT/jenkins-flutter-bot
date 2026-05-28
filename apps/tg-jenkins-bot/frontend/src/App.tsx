/**
 * App — Root component. Manages config fetching, SSE streaming,
 * and provides stack navigation for MainScreen / BuildDetailScreen.
 */

import { useCallback, useEffect, useRef, useState } from 'preact/hooks';
import { useTelegram } from './context/TelegramContext';
import { useSSE } from './hooks/useSSE';
import { useNavigator } from './hooks/useNavigator';
import { fetchConfig, fetchRecentBuilds, ApiError } from './api';
import ErrorBoundary from './components/ErrorBoundary';
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
  const { initData, isTelegram } = useTelegram();
  const navigator = useNavigator();

  const [config, setConfig] = useState<AppConfig | null>(null);
  const [error, setError] = useState<ErrorState | null>(null);

  // Ref mirrors the navigator's current screen for SSE callback
  // (callbacks close over stale hook state without this).
  const currentRef = useRef(navigator.current);
  currentRef.current = navigator.current;

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

  // The active detail screen — either the current screen or the one
  // being animated out (delayed unmount during pop).
  const detailScreen = navigator.current ?? navigator.exiting;

  // CSS class on the viewport controls the transform animation.
  const vpClass = `nav-viewport${navigator.phase !== 'idle' ? ` nav-${navigator.phase}` : ''}`;

  return (
    <div class={vpClass}>
      <div class="nav-screen nav-screen--main">
        <MainScreen
          config={config}
          isActive={navigator.current === null && navigator.exiting === null}
          onBuildSelect={(type, id) =>
            navigator.push({ screen: 'build-detail', type, id })
          }
        />
      </div>
      {detailScreen && (
        <div class="nav-screen nav-screen--detail">
          <BuildDetailScreen
            config={config}
            type={detailScreen.type}
            id={detailScreen.id}
            isActive={navigator.current !== null}
            onBack={() => navigator.pop()}
          />
        </div>
      )}
    </div>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <AppShell />
    </ErrorBoundary>
  );
}
