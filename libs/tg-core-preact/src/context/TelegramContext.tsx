import { useMemo, useEffect, useRef, useState } from 'preact/hooks';
import type { ComponentChildren } from 'preact';
import {
  PlatformContext,
  PrimaryButtonContext,
  PlatformStorageContext,
  type PlatformContextValue,
  type PrimaryButtonRegistry,
  type PlatformStorageProvider,
} from 'platform-core';

/**
 * Concrete Telegram Provider.
 * Enforces a strict Telegram-only runtime environment and exposes native SDK bindings
 * through the provider-agnostic platform-core interfaces.
 */
export function TelegramProvider({ children }: { children: ComponentChildren }) {
  const initializedRef = useRef(false);
  const mainButtonCallbackRef = useRef<(() => void) | null>(null);

  // 1. Enforce strict Telegram-available environment at startup
  if (typeof window !== 'undefined' && !window.Telegram?.WebApp) {
    throw new Error(
      "tg-core-preact error: window.Telegram.WebApp is not available. " +
      "This library is strictly reserved for Telegram-available environments."
    );
  }

  // 2. Memoize native SDK references
  const tg = useMemo(() => (typeof window !== 'undefined' ? window.Telegram?.WebApp : null), []);

  // 3. Track full screen state reactively if supported
  const [isFullscreen, setIsFullscreen] = useState(tg ? !!tg.isFullscreen : false);

  useEffect(() => {
    if (!tg) return;
    const handleFullscreenChange = () => {
      setIsFullscreen(!!tg.isFullscreen);
    };
    tg.onEvent('fullscreenChanged', handleFullscreenChange);
    return () => {
      tg.offEvent('fullscreenChanged', handleFullscreenChange);
    };
  }, [tg]);

  // Bind native MainButton click events to the active component's callback
  useEffect(() => {
    if (!tg) return;
    const handleMainButtonClick = () => {
      mainButtonCallbackRef.current?.();
    };
    tg.onEvent('mainButtonClicked', handleMainButtonClick);
    return () => {
      tg.offEvent('mainButtonClicked', handleMainButtonClick);
    };
  }, [tg]);

  // 4. Map Telegram WebApp SDK directly to PlatformContextValue
  const platformValue = useMemo<PlatformContextValue>(() => {
    if (!tg) {
      return {
        initData: '',
        userId: null,
        hasPhysicalBackButton: false,
        hasNativePrimaryButton: false,
        hasNativePopup: false,
        haptic: {
          impact() {},
          notification() {},
          selectionChanged() {},
        },
        openLink() {},
        isFullscreen: false,
        async requestFullscreen() {},
        async exitFullscreen() {},
        async readClipboardText() { return ''; },
        onLifecycleChange() { return () => {}; },
        showAlert() {},
        async showConfirm() { return false; },
      };
    }

    const initData = tg.initData ?? '';
    const userId = tg.initDataUnsafe?.user?.id ?? null;

    const haptic = {
      impact(style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft') {
        try {
          tg.HapticFeedback.impactOccurred(style);
        } catch { /* noop */ }
      },
      notification(type: 'error' | 'success' | 'warning') {
        try {
          tg.HapticFeedback.notificationOccurred(type);
        } catch { /* noop */ }
      },
      selectionChanged() {
        try {
          tg.HapticFeedback.selectionChanged();
        } catch { /* noop */ }
      },
    };

    const openLink = (url: string, options?: { isExternal?: boolean }) => {
      try {
        if (options?.isExternal || !url.startsWith('tg:') && !url.match(/t\.me/)) {
          if (tg.openLink) {
            tg.openLink(url);
          } else {
            window.open(url, '_blank');
          }
        } else {
          tg.openTelegramLink(url);
        }
      } catch {
        window.open(url, '_blank');
      }
    };

    const requestFullscreen = async () => {
      if (tg.requestFullscreen) {
        tg.requestFullscreen();
      }
    };

    const exitFullscreen = async () => {
      if (tg.exitFullscreen) {
        tg.exitFullscreen();
      }
    };

    const readClipboardText = (): Promise<string> => {
      return new Promise((resolve) => {
        if (tg.readTextFromClipboard) {
          try {
            tg.readTextFromClipboard((text) => resolve(text || ''));
          } catch {
            resolve('');
          }
        } else {
          resolve('');
        }
      });
    };

    const onLifecycleChange = (callback: (state: 'activated' | 'deactivated') => void) => {
      const onAct = () => callback('activated');
      const onDeact = () => callback('deactivated');
      tg.onEvent('activated', onAct);
      tg.onEvent('deactivated', onDeact);
      return () => {
        tg.offEvent('activated', onAct);
        tg.offEvent('deactivated', onDeact);
      };
    };

    const showAlert = (message: string) => {
      try {
        tg.showAlert(message);
      } catch {
        window.alert(message);
      }
    };

    const showConfirm = (options: {
      title: string;
      message: string;
      confirmLabel?: string;
      danger?: boolean;
    }): Promise<boolean> => {
      return new Promise((resolve) => {
        try {
          tg.showPopup({
            title: options.title,
            message: options.message,
            buttons: [
              { id: 'ok', type: options.danger ? 'destructive' : 'default', text: options.confirmLabel || 'OK' },
              { id: 'cancel', type: 'cancel' }
            ]
          }, (buttonId) => {
            resolve(buttonId === 'ok');
          });
        } catch {
          resolve(window.confirm(options.message));
        }
      });
    };

    return {
      initData,
      userId,
      hasPhysicalBackButton: true,
      hasNativePrimaryButton: true,
      hasNativePopup: true,
      haptic,
      openLink,
      isFullscreen,
      requestFullscreen,
      exitFullscreen,
      readClipboardText,
      onLifecycleChange,
      showAlert,
      showConfirm,
    };
  }, [tg, isFullscreen]);

  // 5. Map MainButton to PrimaryButtonRegistry
  const primaryButtonRegistry = useMemo<PrimaryButtonRegistry>(() => {
    if (!tg) {
      return {
        show() {},
        hide() {},
      };
    }

    const btn = tg.MainButton;
    const theme = tg.themeParams;

    return {
      show(config) {
        const color = config.color ?? theme.button_color ?? '#2481cc';
        const textColor = config.textColor ?? theme.button_text_color ?? '#ffffff';

        mainButtonCallbackRef.current = config.onClick;

        btn.setParams({
          text: config.text,
          color,
          text_color: textColor,
          is_active: !config.disabled,
          is_visible: true,
        });

        if (config.loading) {
          btn.showProgress(false);
          btn.disable();
        } else {
          btn.hideProgress();
          if (!config.disabled) {
            btn.enable();
          }
        }
      },
      hide() {
        mainButtonCallbackRef.current = null;
        btn.hideProgress();
        btn.hide();
      },
    };
  }, [tg]);

  // 6. Map CloudStorage to PlatformStorageProvider
  const platformStorageProvider = useMemo<PlatformStorageProvider>(() => {
    if (!tg) {
      return {
        async getItem() { return ''; },
        async setItem() {},
      };
    }

    const cs = tg.CloudStorage;

    return {
      getItem(key: string): Promise<string> {
        return new Promise((resolve, reject) => {
          cs.getItem(key, (err, value) => {
            if (err) reject(new Error(err));
            else resolve(value || '');
          });
        });
      },
      setItem(key: string, value: string): Promise<void> {
        return new Promise((resolve, reject) => {
          cs.setItem(key, value, (err) => {
            if (err) reject(new Error(err));
            else resolve();
          });
        });
      },
    };
  }, [tg]);

  // 7. Perform native Telegram SDK startup optimization hooks on mount
  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;

    if (tg) {
      tg.ready();
      tg.expand();
      tg.disableVerticalSwipes?.();
      if (tg.setBottomBarColor) tg.setBottomBarColor('secondary_bg_color');

      tg.setHeaderColor('secondary_bg_color');
      tg.setBackgroundColor('secondary_bg_color');
    }
  }, [tg]);

  return (
    <PlatformContext.Provider value={platformValue}>
      <PrimaryButtonContext.Provider value={primaryButtonRegistry}>
        <PlatformStorageContext.Provider value={platformStorageProvider}>
          {children}
        </PlatformStorageContext.Provider>
      </PrimaryButtonContext.Provider>
    </PlatformContext.Provider>
  );
}
