/**
 * useCloudStorage — Reactive read/write for Telegram CloudStorage keys.
 *
 * Wraps the callback-based CloudStorage API with a hook that returns
 * [value, setValue, loading]. Falls back to the default value when
 * CloudStorage is unavailable or on error.
 */

import { useCallback, useEffect, useState } from 'preact/hooks';
import { useTelegram } from '../context/TelegramContext';

/** Read a value from CloudStorage as a Promise. */
function csGet(cs: TelegramCloudStorage, key: string): Promise<string> {
  return new Promise((resolve, reject) => {
    cs.getItem(key, (err, value) => {
      if (err) reject(new Error(err));
      else resolve(value);
    });
  });
}

/** Write a value to CloudStorage as a Promise. */
function csSet(cs: TelegramCloudStorage, key: string, value: string): Promise<void> {
  return new Promise((resolve, reject) => {
    cs.setItem(key, value, (err) => {
      if (err) reject(new Error(err));
      else resolve();
    });
  });
}

/**
 * Persist a JSON-serializable value in Telegram CloudStorage.
 *
 * @param key       CloudStorage key (1–128 chars, [A-Za-z0-9_-])
 * @param fallback  Default value used until loaded and when CloudStorage is unavailable
 * @returns         [value, setValue, loading]
 */
export function useCloudStorage<T>(key: string, fallback: T): [T, (v: T) => void, boolean] {
  const { tg } = useTelegram();
  const [value, setLocal] = useState<T>(fallback);
  const [loading, setLoading] = useState(true);

  // Load on mount
  useEffect(() => {
    const cs = tg?.CloudStorage;
    if (!cs) {
      setLoading(false);
      return;
    }

    csGet(cs, key)
      .then((raw) => {
        if (raw) {
          try { setLocal(JSON.parse(raw) as T); }
          catch { /* invalid stored value — keep fallback */ }
        }
      })
      .catch(() => { /* CloudStorage unavailable — keep fallback */ })
      .finally(() => setLoading(false));
  }, [tg, key]);

  // Setter writes to CloudStorage and updates local state
  const setValue = useCallback((next: T) => {
    setLocal(next);
    const cs = tg?.CloudStorage;
    if (cs) {
      csSet(cs, key, JSON.stringify(next)).catch(() => {
        /* best-effort — local state is already updated */
      });
    }
  }, [tg, key]);

  return [value, setValue, loading];
}
