/**
 * ToastContext — Global toast notification system.
 *
 * Wraps the app in a provider that exposes showToast().
 * Toasts auto-dismiss after 3 seconds.
 */

import { createContext } from 'preact';
import { useCallback, useContext, useState } from 'preact/hooks';
import type { ComponentChildren } from 'preact';

type ToastType = 'success' | 'error' | 'info';

interface Toast {
  id: number;
  message: string;
  type: ToastType;
  visible: boolean;
}

interface ToastContextValue {
  showToast: (message: string, type?: ToastType) => void;
}

const ToastContext = createContext<ToastContextValue>({
  showToast: () => {},
});

let nextId = 0;

export function ToastProvider({ children }: { children: ComponentChildren }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const showToast = useCallback((message: string, type: ToastType = 'success') => {
    const id = nextId++;
    const toast: Toast = { id, message, type, visible: false };

    setToasts((prev) => [...prev, toast]);

    // Trigger enter animation
    requestAnimationFrame(() => {
      setToasts((prev) =>
        prev.map((t) => (t.id === id ? { ...t, visible: true } : t)),
      );
    });

    // Auto-dismiss after 3 seconds
    setTimeout(() => {
      setToasts((prev) =>
        prev.map((t) => (t.id === id ? { ...t, visible: false } : t)),
      );
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, 200);
    }, 3000);
  }, []);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div class="toast-container">
        {toasts.map((t) => (
          <div
            key={t.id}
            class={`toast toast--${t.type}${t.visible ? ' visible' : ''}`}
          >
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
