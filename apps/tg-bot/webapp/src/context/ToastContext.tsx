/**
 * ToastContext — Provides a showToast() function to any component.
 *
 * The Toast component renders inside this provider. Any child can
 * call showToast() without prop drilling.
 */

import { createContext } from 'preact';
import { useCallback, useContext, useRef } from 'preact/hooks';
import { signal } from '@preact/signals';
import type { ComponentChildren } from 'preact';
import Toast from '../components/Toast';

interface ToastState {
  message: string;
  type: 'success' | 'error';
  visible: boolean;
}

interface ToastContextValue {
  showToast(message: string, type?: 'success' | 'error'): void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const toastState = signal<ToastState>({
  message: '',
  type: 'success',
  visible: false,
});

export function ToastProvider({ children }: { children: ComponentChildren }) {
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = useCallback((message: string, type: 'success' | 'error' = 'success') => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);

    toastState.value = { message, type, visible: true };

    timeoutRef.current = setTimeout(() => {
      toastState.value = { ...toastState.value, visible: false };
    }, 4000);
  }, []);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <Toast state={toastState} />
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within ToastProvider');
  return ctx;
}
