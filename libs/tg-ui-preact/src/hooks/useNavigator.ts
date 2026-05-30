import { useCallback, useRef, useState } from 'preact/hooks';

export const NAV_TRANSITION_MS = 300;

export type NavPhase = 'idle' | 'pushing' | 'pushed' | 'popping';

export interface NavigatorState<S> {
  /** The active screen, or null if at root. */
  current: S | null;
  /** The screen being animated out (stays mounted during exit). */
  exiting: S | null;
  /** Current animation phase for CSS class binding. */
  phase: NavPhase;
  /** Push a screen on top (slide-in-from-right). */
  push(screen: S): void;
  /** Pop the topmost screen (slide-out-to-right, delayed unmount). */
  pop(): void;
  /** Replace the topmost screen's data instantly without animation. */
  replace(screen: S): void;
}

export function useNavigator<S = any>(): NavigatorState<S> {
  const [current, setCurrent] = useState<S | null>(null);
  const [exiting, setExiting] = useState<S | null>(null);
  const [phase, setPhase] = useState<NavPhase>('idle');

  // Guard against concurrent transition triggers
  const animatingRef = useRef(false);

  const push = useCallback((screen: S) => {
    if (animatingRef.current) return;
    animatingRef.current = true;

    setCurrent(screen);
    setPhase('pushing');

    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        setPhase('pushed');
        setTimeout(() => {
          animatingRef.current = false;
        }, NAV_TRANSITION_MS);
      });
    });
  }, []);

  const pop = useCallback(() => {
    if (animatingRef.current || !current) return;
    animatingRef.current = true;

    setExiting(current);
    setCurrent(null);
    setPhase('popping');

    setTimeout(() => {
      setExiting(null);
      setPhase('idle');
      animatingRef.current = false;
    }, NAV_TRANSITION_MS);
  }, [current]);

  const replace = useCallback((screen: S) => {
    setCurrent(screen);
  }, []);

  return { current, exiting, phase, push, pop, replace };
}
