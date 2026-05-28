/**
 * App — Root component. Manages config fetching, SSE streaming,
 * and provides the router for MainScreen / BuildDetailScreen navigation.
 */

import { useCallback, useEffect, useRef, useState } from 'preact/hooks';
import { Router, useLocation, useRoute } from 'wouter-preact';
import { useTelegram } from './context/TelegramContext';
import { useSSE } from './hooks/useSSE';
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

/** Inner app wrapped by the Router — has access to useLocation(). */
function AppShell() {
  const { initData, isTelegram } = useTelegram();
  const [, navigate] = useLocation();

  const [config, setConfig] = useState<AppConfig | null>(null);
  const [error, setError] = useState<ErrorState | null>(null);

  // Keep a ref to current location for SSE auto-transition
  const locationRef = useRef('/');
  const [location] = useLocation();
  locationRef.current = location;

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

    // Auto-transition: if viewing an active build detail and it just completed,
    // fetch recent builds and switch to the completed result screen.
    const currentPath = locationRef.current;
    const activeMatch = currentPath.match(/^\/build\/active\/(.+)$/);
    if (activeMatch) {
      const viewingRequestId = decodeURIComponent(activeMatch[1]!);
      const stillActive = builds.some((b) => b.request_id === viewingRequestId);
      if (!stillActive) {
        fetchRecentBuilds(initData)
          .then((recent) => {
            const match = recent.find((r) => r.request_id === viewingRequestId);
            if (match) {
              navigate(`/build/recent/${encodeURIComponent(match.request_id)}`, { replace: true });
            } else {
              // Build completed but not yet in recent — return to main
              navigate('/', { replace: true });
            }
          })
          .catch(() => {
            // Fetch failed — return to main screen gracefully
            navigate('/', { replace: true });
          });
      }
    }
  }, [initData, navigate]);

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

  // MainScreen stays mounted to preserve state (branch selection, scroll, etc.).
  // Hidden via CSS when viewing a build detail route.
  const [isDetailRoute, detailParams] = useRoute('/build/:type/:id');

  return (
    <>
      <div style={{ display: isDetailRoute ? 'none' : 'contents' }}>
        <MainScreen config={config} />
      </div>
      {isDetailRoute && detailParams && (
        <BuildDetailScreen
          config={config}
          type={detailParams.type as 'active' | 'recent'}
          id={decodeURIComponent(detailParams.id)}
        />
      )}
    </>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <Router base="/webapp">
        <AppShell />
      </Router>
    </ErrorBoundary>
  );
}
