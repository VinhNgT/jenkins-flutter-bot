/**
 * useSSE — Manages EventSource lifecycle with visibility-aware debouncing.
 *
 * Creates a single SSE connection to the active builds stream endpoint.
 * Automatically pauses when the app is backgrounded (via visibilitychange,
 * pagehide/pageshow, and Telegram activated/deactivated events) and
 * resumes when foregrounded — with a readyState guard to prevent the
 * concurrent reconnection bug that caused stream cancellation log spam.
 */

import { useEffect, useRef } from 'preact/hooks';
import type { ActiveBuild, RecentBuild } from '../types';

export function useSSE(
  url: string | null,
  onBuilds: (builds: ActiveBuild[]) => void,
  onRecentBuilds: (builds: RecentBuild[]) => void,
): void {
  const esRef = useRef<EventSource | null>(null);
  const onBuildsRef = useRef(onBuilds);
  onBuildsRef.current = onBuilds;

  const onRecentBuildsRef = useRef(onRecentBuilds);
  onRecentBuildsRef.current = onRecentBuilds;

  useEffect(() => {
    if (!url) return;

    function start() {
      // Debounce guard: prevent multiple simultaneous connections when
      // visibility events (visibilitychange, pageshow, activated) fire
      // concurrently on foregrounding.
      const es = esRef.current;
      if (es && (es.readyState === EventSource.CONNECTING || es.readyState === EventSource.OPEN)) {
        return;
      }

      if (es) es.close();

      const newEs = new EventSource(url!);
      esRef.current = newEs;

      newEs.addEventListener('builds', (event) => {
        try {
          const builds = JSON.parse((event as MessageEvent).data) as ActiveBuild[];
          onBuildsRef.current(builds);
        } catch (err) {
          console.error('Failed parsing SSE payload:', err);
        }
      });

      newEs.addEventListener('recent', (event) => {
        try {
          const builds = JSON.parse((event as MessageEvent).data) as RecentBuild[];
          onRecentBuildsRef.current(builds);
        } catch (err) {
          console.error('Failed parsing SSE payload:', err);
        }
      });

      newEs.onerror = () => {
        console.warn('EventSource disconnected. Retrying natively...');
      };
    }

    function stop() {
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
    }

    function handleVisibility() {
      if (document.hidden) {
        stop();
      } else {
        start();
      }
    }

    function handlePageShow() {
      if (!document.hidden) start();
    }

    // Initial connection
    start();

    // Register all visibility lifecycle handlers
    document.addEventListener('visibilitychange', handleVisibility);
    window.addEventListener('pagehide', stop);
    window.addEventListener('pageshow', handlePageShow);

    // Telegram-specific lifecycle events
    const tg = window.Telegram?.WebApp;
    const handleActivated = () => start();
    const handleDeactivated = () => stop();

    if (tg?.onEvent) {
      tg.onEvent('activated', handleActivated);
      tg.onEvent('deactivated', handleDeactivated);
    }

    return () => {
      stop();
      document.removeEventListener('visibilitychange', handleVisibility);
      window.removeEventListener('pagehide', stop);
      window.removeEventListener('pageshow', handlePageShow);
      if (tg?.offEvent) {
        tg.offEvent('activated', handleActivated);
        tg.offEvent('deactivated', handleDeactivated);
      }
    };
  }, [url]);
}
