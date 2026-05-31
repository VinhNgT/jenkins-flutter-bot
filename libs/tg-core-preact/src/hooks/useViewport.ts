import { useEffect, useState } from 'preact/hooks';

export interface ViewportState {
  height: number;
  isExpanded: boolean;
}

export function useViewport(options?: {
  disableSwipes?: boolean;
}): ViewportState {
  const [viewport, setViewport] = useState<ViewportState>({
    height: typeof window !== 'undefined' ? window.innerHeight : 0,
    isExpanded: true,
  });

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const tg = window.Telegram?.WebApp;
    if (!tg) return;

    tg.expand();

    if (options?.disableSwipes) {
      tg.disableVerticalSwipes?.();
    } else {
      tg.enableVerticalSwipes?.();
    }

    const handleResize = () => {
      setViewport({
        height: window.innerHeight,
        isExpanded: true,
      });
    };

    window.addEventListener('resize', handleResize);
    tg.onEvent('viewportChanged', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      tg.offEvent('viewportChanged', handleResize);
    };
  }, [options?.disableSwipes]);

  return viewport;
}
