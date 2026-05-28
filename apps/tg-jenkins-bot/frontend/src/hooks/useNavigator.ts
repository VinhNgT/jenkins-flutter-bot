/**
 * useNavigator — Flutter-style stack navigation with View Transitions.
 *
 * Manages an overlay stack on top of the always-mounted MainScreen.
 * Push slides a new screen in from the right; pop slides it out to
 * the right — matching iOS/Telegram navigation conventions.
 *
 * Uses the View Transitions API for directional animations when
 * available. Falls back to instant DOM updates on older WebViews.
 * Respects `prefers-reduced-motion` via CSS (see navigator.css).
 */

import { useCallback, useRef, useState } from 'preact/hooks';

/** A screen pushed onto the navigation stack. */
export interface Screen {
  screen: 'build-detail';
  type: 'active' | 'recent';
  id: string;
}

export interface Navigator {
  /** Current overlay stack (empty = MainScreen only). */
  stack: Screen[];
  /** The topmost pushed screen, or null if at root. */
  current: Screen | null;
  /** Push a screen on top (slide-in-from-right). */
  push(screen: Screen): void;
  /** Pop the topmost screen (slide-out-to-right). */
  pop(): void;
  /** Replace the topmost screen without animation. */
  replace(screen: Screen): void;
}

/**
 * Wraps a DOM-mutating callback in a View Transition with a
 * directional type ('forward' or 'backward'). Falls back to
 * calling the callback directly if the API is unavailable.
 */
function withTransition(
  direction: 'forward' | 'backward',
  callback: () => void,
): void {
  const doc = document as Document & {
    startViewTransition?: (opts: {
      update: () => void;
      types: string[];
    }) => unknown;
  };

  if (!doc.startViewTransition) {
    callback();
    return;
  }

  doc.startViewTransition({
    update: callback,
    types: [direction],
  });
}

export function useNavigator(): Navigator {
  const [stack, setStack] = useState<Screen[]>([]);

  // Ref mirrors the latest stack for use inside transition callbacks,
  // which close over stale state without it.
  const stackRef = useRef(stack);
  stackRef.current = stack;

  const push = useCallback((screen: Screen) => {
    withTransition('forward', () => {
      setStack((prev) => [...prev, screen]);
    });
  }, []);

  const pop = useCallback(() => {
    withTransition('backward', () => {
      setStack((prev) => (prev.length > 0 ? prev.slice(0, -1) : prev));
    });
  }, []);

  const replace = useCallback((screen: Screen) => {
    setStack((prev) => {
      if (prev.length === 0) return [screen];
      return [...prev.slice(0, -1), screen];
    });
  }, []);

  const current = stack.length > 0 ? stack[stack.length - 1]! : null;

  return { stack, current, push, pop, replace };
}
