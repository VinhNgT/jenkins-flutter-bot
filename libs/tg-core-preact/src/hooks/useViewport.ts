import { useEffect, useState } from 'preact/hooks';

export interface ViewportState {
  height: number;
  isExpanded: boolean;
}

export function useViewport(options?: {
  disableSwipes?: boolean;
}): ViewportState {
  const tg = typeof window !== 'undefined' ? window.Telegram?.WebApp : null;
  const isTelegram = !!(tg && tg.initData && tg.initData !== 'preview');
  const [viewport, setViewport] = useState<ViewportState>({
    height: window.innerHeight,
    isExpanded: true,
  });

  useEffect(() => {
    if (!isTelegram || !tg) return;

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
  }, [tg, isTelegram, options?.disableSwipes]);

  return viewport;
}
