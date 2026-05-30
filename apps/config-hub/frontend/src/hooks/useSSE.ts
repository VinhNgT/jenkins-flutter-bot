/**
 * useSSE — Manages EventSource lifecycle for service status streaming.
 *
 * Creates a single SSE connection to the config-hub status stream.
 * Automatically pauses when the page is backgrounded (via visibilitychange)
 * and resumes when foregrounded — with a readyState guard to prevent
 * concurrent reconnection bugs.
 *
 * Unlike the bot webapp's useSSE (which handles Telegram lifecycle events),
 * config-hub only needs standard browser visibility handling since it runs
 * in a standalone browser tab.
 */

import { useEffect, useRef } from 'preact/hooks';
import type { ServiceStatuses } from '../types';

export function useSSE(
  url: string | null,
  onStatus: (statuses: ServiceStatuses) => void,
): void {
  const esRef = useRef<EventSource | null>(null);
  const onStatusRef = useRef(onStatus);
  onStatusRef.current = onStatus;

  useEffect(() => {
    if (!url) return;

    function start() {
      // Debounce guard: prevent multiple simultaneous connections when
      // visibility events fire concurrently on foregrounding.
      const es = esRef.current;
      if (es && (es.readyState === EventSource.CONNECTING || es.readyState === EventSource.OPEN)) {
        return;
      }

      if (es) es.close();

      const newEs = new EventSource(url!);
      esRef.current = newEs;

      newEs.addEventListener('status', (event) => {
        try {
          const statuses = JSON.parse((event as MessageEvent).data) as ServiceStatuses;
          onStatusRef.current(statuses);
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

    // Register visibility lifecycle handlers
    document.addEventListener('visibilitychange', handleVisibility);
    window.addEventListener('pagehide', stop);
    window.addEventListener('pageshow', handlePageShow);

    return () => {
      stop();
      document.removeEventListener('visibilitychange', handleVisibility);
      window.removeEventListener('pagehide', stop);
      window.removeEventListener('pageshow', handlePageShow);
    };
  }, [url]);
}
