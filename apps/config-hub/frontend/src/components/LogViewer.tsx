/**
 * LogViewer — Terminal-style log viewer for service ring buffer output.
 *
 * Inspired by GitHub Actions log panels: dark terminal background,
 * monospace font, line numbers, log-level coloring, and auto-scroll.
 * Fetches logs on mount and auto-refreshes every 3 seconds.
 */

import { RefreshCw, ArrowDownToLine, X } from 'lucide-preact';
import { useCallback, useEffect, useRef, useState } from 'preact/hooks';
import { API } from '../api';
import type { Scope } from '../types';

interface LogViewerProps {
  scope: Scope;
  onClose: () => void;
}

/** Classify a log line by its Python log level for color-coding. */
function logLevel(line: string): 'error' | 'warning' | 'info' | 'debug' | null {
  // Standard Python logging format: "YYYY-MM-DD HH:MM:SS,ms - name - LEVEL - msg"
  // Also handle simpler "LEVEL:" prefix patterns.
  if (/\b(ERROR|CRITICAL)\b/.test(line)) return 'error';
  if (/\bWARNING\b/.test(line)) return 'warning';
  if (/\bDEBUG\b/.test(line)) return 'debug';
  if (/\bINFO\b/.test(line)) return 'info';
  return null;
}

export default function LogViewer({ scope, onClose }: LogViewerProps) {
  const [lines, setLines] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [autoScroll, setAutoScroll] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);

  const fetchLogs = useCallback(async () => {
    const result = await API.getServiceLogs(scope);
    if (result) {
      setLines(result.lines);
      setLoading(false);
    }
  }, [scope]);

  // Initial fetch + auto-refresh every 3 seconds
  useEffect(() => {
    fetchLogs();
    const id = setInterval(fetchLogs, 3000);
    return () => clearInterval(id);
  }, [fetchLogs]);

  // Auto-scroll to bottom when new lines arrive
  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [lines, autoScroll]);

  // Detect manual scroll-up to pause auto-scroll
  function handleScroll() {
    const el = containerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    setAutoScroll(atBottom);
  }

  function scrollToBottom() {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
      setAutoScroll(true);
    }
  }

  return (
    <div class="log-viewer">
      <div class="log-viewer__toolbar">
        <span class="log-viewer__title">Service Logs</span>
        <div class="log-viewer__actions">
          <button
            class="log-viewer__btn"
            onClick={() => fetchLogs()}
            title="Refresh"
          >
            <RefreshCw size={14} />
          </button>
          <button
            class="log-viewer__btn"
            onClick={scrollToBottom}
            title="Scroll to bottom"
            disabled={autoScroll}
          >
            <ArrowDownToLine size={14} />
          </button>
          <button
            class="log-viewer__btn log-viewer__btn--close"
            onClick={onClose}
            title="Close"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      <div
        class="log-viewer__output"
        ref={containerRef}
        onScroll={handleScroll}
      >
        {loading ? (
          <div class="log-viewer__empty">Loading logs…</div>
        ) : lines.length === 0 ? (
          <div class="log-viewer__empty">No log output yet.</div>
        ) : (
          <table class="log-viewer__table">
            <tbody>
              {lines.map((line, i) => {
                const level = logLevel(line);
                return (
                  <tr
                    key={i}
                    class={`log-line ${level ? `log-line--${level}` : ''}`}
                  >
                    <td class="log-line__num">{i + 1}</td>
                    <td class="log-line__text">{line}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
