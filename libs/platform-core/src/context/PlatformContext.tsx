import { createContext } from 'preact';
import { useContext, useEffect, useMemo, useState } from 'preact/hooks';
import type { ComponentChildren } from 'preact';

export interface PlatformContextValue {
  initData: string;
  userId: number | null;
  hasPhysicalBackButton: boolean;
  hasNativePrimaryButton: boolean;
  hasNativePopup: boolean;
  haptic: {
    impact(style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft'): void;
    notification(type: 'error' | 'success' | 'warning'): void;
    selectionChanged(): void;
  };
  openLink(url: string, options?: { isExternal?: boolean }): void;
  isFullscreen: boolean;
  requestFullscreen(): Promise<void>;
  exitFullscreen(): Promise<void>;
  readClipboardText(): Promise<string>;
  onLifecycleChange(callback: (state: 'activated' | 'deactivated') => void): () => void;
  showAlert(message: string): void;
  showConfirm(options: {
    title: string;
    message: string;
    confirmLabel?: string | undefined;
    danger?: boolean | undefined;
  }): Promise<boolean>;
}

export const PlatformContext = createContext<PlatformContextValue | null>(null);

/**
 * Access the core capability-based platform context.
 */
export function usePlatform(): PlatformContextValue {
  const ctx = useContext(PlatformContext);
  if (!ctx) {
    throw new Error('usePlatform must be used within PlatformProvider');
  }
  return ctx;
}

/**
 * Default browser-native platform provider.
 * Implements W3C WAM / HTML5 standard capabilities for standalone web engines.
 */
export function BrowserPlatformProvider({ children }: { children: ComponentChildren }) {
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    if (typeof document === 'undefined') return;
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => {
      document.removeEventListener('fullscreenchange', handleFullscreenChange);
    };
  }, []);

  const platformValue = useMemo<PlatformContextValue>(() => {
    return {
      initData: '',
      userId: null,
      hasPhysicalBackButton: false,
      hasNativePrimaryButton: false,
      hasNativePopup: false,
      haptic: {
        impact(style) {
          console.log(`📳 [Browser Haptic] impact: ${style}`);
          try {
            const d = style === 'heavy' ? 40 : style === 'medium' ? 25 : 12;
            navigator.vibrate?.(d);
          } catch { /* noop */ }
        },
        notification(type) {
          console.log(`📳 [Browser Haptic] notification: ${type}`);
          try {
            const d = type === 'error' ? 60 : type === 'warning' ? 40 : 20;
            navigator.vibrate?.(d);
          } catch { /* noop */ }
        },
        selectionChanged() {
          console.log('📳 [Browser Haptic] selectionChanged');
          try {
            navigator.vibrate?.(10);
          } catch { /* noop */ }
        },
      },
      openLink(url) {
        window.open(url, '_blank');
      },
      isFullscreen,
      async requestFullscreen() {
        if (document.documentElement.requestFullscreen) {
          await document.documentElement.requestFullscreen();
        }
      },
      async exitFullscreen() {
        if (document.exitFullscreen) {
          await document.exitFullscreen();
        }
      },
      async readClipboardText() {
        if (navigator.clipboard?.readText) {
          return await navigator.clipboard.readText();
        }
        return '';
      },
      onLifecycleChange(callback) {
        const handleVisibilityChange = () => {
          callback(document.visibilityState === 'visible' ? 'activated' : 'deactivated');
        };
        document.addEventListener('visibilitychange', handleVisibilityChange);
        return () => {
          document.removeEventListener('visibilitychange', handleVisibilityChange);
        };
      },
      showAlert(message) {
        window.alert(message);
      },
      showConfirm(options) {
        return Promise.resolve(window.confirm(options.message));
      },
    };
  }, [isFullscreen]);

  return (
    <PlatformContext.Provider value={platformValue}>
      {children}
    </PlatformContext.Provider>
  );
}
