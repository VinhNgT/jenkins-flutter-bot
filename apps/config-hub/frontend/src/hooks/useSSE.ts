/**
 * useSSE — Server-Sent Events hook.
 *
 * Connects to a stream URL and calls onMessage for each parsed event.
 * Supports both unnamed (onmessage) and named events.
 * Reconnects automatically via EventSource's built-in retry.
 * Pauses when the browser tab is hidden to save resources.
 */

import { useEffect, useRef } from 'preact/hooks';

interface UseSSEOptions {
  /** Named event to listen for (e.g. 'status'). Omit for default unnamed events. */
  eventName?: string;
}

export function useSSE<T>(
  url: string | null,
  onMessage: (data: T) => void,
  options?: UseSSEOptions,
): void {
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const eventName = options?.eventName;

  useEffect(() => {
    if (!url) return;

    let es: EventSource | null = null;

    function handleEvent(event: MessageEvent) {
      try {
        const data = JSON.parse(event.data) as T;
        onMessageRef.current(data);
      } catch {
        // Ignore malformed events
      }
    }

    function connect() {
      if (es) return;
      es = new EventSource(url!);

      if (eventName) {
        es.addEventListener(eventName, handleEvent);
      } else {
        es.onmessage = handleEvent;
      }

      es.onerror = () => {
        // EventSource auto-reconnects; log for debugging
        console.warn('SSE connection error, will auto-reconnect');
      };
    }

    function disconnect() {
      if (es) {
        if (eventName) {
          es.removeEventListener(eventName, handleEvent);
        }
        es.close();
        es = null;
      }
    }

    function onVisibility() {
      if (document.hidden) {
        disconnect();
      } else {
        connect();
      }
    }

    connect();
    document.addEventListener('visibilitychange', onVisibility);

    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      disconnect();
    };
  }, [url, eventName]);
}
