/**
 * useRelativeTime — Returns a live-updating relative time string.
 *
 * Replaces the manual setInterval + querySelectorAll('.relative-time-ticker')
 * pattern from the vanilla JS implementation. Each component instance manages
 * its own interval, cleaned up automatically on unmount.
 */

import { useEffect, useState } from 'preact/hooks';

function formatRelativeTime(timestamp: number): string {
  const diffSec = Math.floor(Date.now() / 1000 - timestamp);
  if (diffSec < 60) return 'just now';
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  return `${Math.floor(diffSec / 86400)}d ago`;
}

export function useRelativeTime(timestamp: number): string {
  const [text, setText] = useState(() => formatRelativeTime(timestamp));

  useEffect(() => {
    setText(formatRelativeTime(timestamp));

    const interval = setInterval(() => {
      setText(formatRelativeTime(timestamp));
    }, 2000);

    return () => clearInterval(interval);
  }, [timestamp]);

  return text;
}
