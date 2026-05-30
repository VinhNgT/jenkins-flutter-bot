import { createContext } from 'preact';
import { useCallback, useEffect, useState, useContext } from 'preact/hooks';

export interface PlatformStorageProvider {
  getItem(key: string): Promise<string>;
  setItem(key: string, value: string): Promise<void>;
}

export const PlatformStorageContext = createContext<PlatformStorageProvider | null>(null);

/**
 * Persist a JSON-serializable value in platform cloud storage with local fallback.
 */
export function usePlatformStorage<T>(
  key: string,
  fallback: T,
): [T, (v: T) => void, boolean] {
  const storage = useContext(PlatformStorageContext);
  const [value, setValueState] = useState<T>(fallback);
  const [loading, setLoading] = useState(true);

  // Load value on mount
  useEffect(() => {
    if (!storage) {
      // Graceful local standard browser localStorage fallback
      try {
        const stored = localStorage.getItem(key);
        if (stored) {
          setValueState(JSON.parse(stored) as T);
        }
      } catch { /* noop */ }
      setLoading(false);
      return;
    }

    storage.getItem(key)
      .then((raw) => {
        if (raw) {
          try {
            setValueState(JSON.parse(raw) as T);
          } catch { /* keep fallback */ }
        }
      })
      .catch(() => { /* keep fallback */ })
      .finally(() => setLoading(false));
  }, [storage, key]);

  // Update value callback
  const setValue = useCallback((next: T) => {
    setValueState(next);
    if (storage) {
      storage.setItem(key, JSON.stringify(next)).catch(() => {
        /* best-effort */
      });
    } else {
      try {
        localStorage.setItem(key, JSON.stringify(next));
      } catch { /* noop */ }
    }
  }, [storage, key]);

  return [value, setValue, loading];
}
