/**
 * App — Root component. Manages config fetching, SSE streaming,
 * and provides stack navigation for MainScreen / BuildDetailScreen.
 */

import { useCallback, useEffect, useRef, useState } from 'preact/hooks';
import { usePlatform } from 'platform-core';
import { useNavigator, Navigator, ErrorBoundary } from 'tg-ui-preact';
import { useSSE } from './hooks/useSSE';
import { createAPI, ApiError } from './api';
import { ApiProvider, useAPI } from './context/ApiContext';
import LoadingScreen from './components/LoadingScreen';
import ErrorScreen from './components/ErrorScreen';
import MainScreen from './components/MainScreen';
import BuildDetailScreen from './components/BuildDetailScreen';
import type { ActiveBuild, AppConfig, ApiErrorDetail, RecentBuild } from './types';

interface ErrorState {
  title: string;
  description: string;
  detail: ApiErrorDetail | null;
}

function AppShell() {
  const api = useAPI();
  const platform = usePlatform();
  const { initData } = platform;
  const navigator = useNavigator();

  const [config, setConfig] = useState<AppConfig | null>(null);
  const [activeBuilds, setActiveBuilds] = useState<ActiveBuild[]>([]);
  const [error, setError] = useState<ErrorState | null>(null);

  // Ref mirrors the navigator's current screen for SSE callback
  // (callbacks close over stale hook state without this).
  const currentRef = useRef(navigator.current);
  currentRef.current = navigator.current;

  // Fetch initial config
  useEffect(() => {
    api.fetchConfig()
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
  }, [initData]);

  const [recentBuilds, setRecentBuilds] = useState<RecentBuild[]>([]);
  const recentBuildsRef = useRef<RecentBuild[]>([]);

  const handleRecentBuildsUpdate = useCallback((recent: RecentBuild[]) => {
    recentBuildsRef.current = recent;
    setRecentBuilds((prev) => {
      if (JSON.stringify(prev) === JSON.stringify(recent)) return prev;
      return recent;
    });
  }, []);

  // SSE stream for active and recent builds — only when config is loaded
  const sseUrl = config ? `/api/webapp/stream?init_data=${encodeURIComponent(initData)}` : null;

  const handleBuildsUpdate = useCallback((builds: ActiveBuild[]) => {
    setActiveBuilds((prev) => {
      if (JSON.stringify(prev) === JSON.stringify(builds)) return prev;
      return builds;
    });

    // Auto-transition: if viewing an active build detail and it just
    // completed, use the streamed recent builds and switch to the result screen.
    const viewing = currentRef.current;
    if (viewing?.type === 'active') {
      const stillActive = builds.some((b) => b.request_id === viewing.id);
      if (!stillActive) {
        setTimeout(() => {
          const match = recentBuildsRef.current.find((r) => r.request_id === viewing.id);
          if (match) {
            navigator.replace({ screen: 'build-detail', type: 'recent', id: match.request_id });
          } else {
            // Build completed but not in recent yet — return to main
            navigator.pop();
          }
        }, 50);
      }
    }
  }, [navigator]);

  useSSE(sseUrl, handleBuildsUpdate, handleRecentBuildsUpdate);


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
          activeBuilds={activeBuilds}
          recentBuilds={recentBuilds}
          onBuildSelect={(type, id) =>
            navigator.push({ screen: 'build-detail', type, id })
          }
        />
      }
      detailScreen={
        navigator.current ? (
          <BuildDetailScreen
            activeBuilds={activeBuilds}
            recentBuilds={recentBuilds}
            type={navigator.current.type}
            id={navigator.current.id}
            onBack={() => navigator.pop()}
          />
        ) : null
      }
      exitingScreen={
        navigator.exiting ? (
          <BuildDetailScreen
            activeBuilds={activeBuilds}
            recentBuilds={recentBuilds}
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
  const platform = usePlatform();
  const api = createAPI(platform.initData);

  return (
    <ErrorBoundary>
      <ApiProvider api={api}>
        <AppShell />
      </ApiProvider>
    </ErrorBoundary>
  );
}
