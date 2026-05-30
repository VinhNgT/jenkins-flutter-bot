/**
 * useNavigator — CSS transform-based stack navigation for config-hub.
 *
 * Manages an overlay stack on top of the always-mounted HomeScreen.
 * Push slides a new screen in from the right; pop slides it out to
 * the right — matching iOS/Telegram navigation conventions.
 *
 * Uses CSS transforms + transitions (not the View Transitions API).
 *
 * Implements delayed unmount: on pop, the exiting screen stays in
 * the DOM during the slide-out animation and is only removed after
 * the transition completes.
 */

import { useCallback, useRef, useState } from 'preact/hooks';

/** Shared transition duration (ms). Used in both JS setTimeout and
 *  CSS via the `--nav-transition-ms` custom property. */
export const NAV_TRANSITION_MS = 300;

/** Config-hub screen types. */
export type ScreenType = 'config' | 'tools';

/** A screen pushed onto the navigation stack. */
export interface Screen {
  screen: ScreenType;
  /** Section ID for config screens (e.g., 'telegram', 'jenkins', 'storage') */
  id?: string;
}

/** Navigator phase for CSS class application. */
export type NavPhase = 'idle' | 'pushing' | 'pushed' | 'popping';

export interface Navigator {
  /** The active screen, or null if at root. */
  current: Screen | null;
  /** The screen being animated out (stays mounted during exit). */
  exiting: Screen | null;
  /** Current animation phase for CSS class binding. */
  phase: NavPhase;
  /** Push a screen on top (slide-in-from-right). */
  push(screen: Screen): void;
  /** Pop the topmost screen (slide-out-to-right, delayed unmount). */
  pop(): void;
  /** Replace the topmost screen's data without animation. */
  replace(screen: Screen): void;
}

export function useNavigator(): Navigator {
  const [current, setCurrent] = useState<Screen | null>(null);
  const [exiting, setExiting] = useState<Screen | null>(null);
  const [phase, setPhase] = useState<NavPhase>('idle');

  // Guard against concurrent push/pop operations.
  const animatingRef = useRef(false);

  const push = useCallback((screen: Screen) => {
    if (animatingRef.current) return;
    animatingRef.current = true;

    // Mount the detail screen offscreen (CSS positions it at translateX(100%))
    setCurrent(screen);
    setPhase('pushing');

    // After one frame (so the browser paints the offscreen position),
    // trigger the slide-in by switching to 'pushed' phase.
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        setPhase('pushed');

        // After the transition completes, settle into idle.
        setTimeout(() => {
          animatingRef.current = false;
        }, NAV_TRANSITION_MS);
      });
    });
  }, []);

  const pop = useCallback(() => {
    if (animatingRef.current || !current) return;
    animatingRef.current = true;

    // Move current to exiting (keeps it mounted during animation)
    setExiting(current);
    setCurrent(null);
    setPhase('popping');

    // After the slide-out transition completes, unmount the exiting screen.
    setTimeout(() => {
      setExiting(null);
      setPhase('idle');
      animatingRef.current = false;
    }, NAV_TRANSITION_MS);
  }, [current]);

  const replace = useCallback((screen: Screen) => {
    // Instant data swap — no animation.
    setCurrent(screen);
  }, []);

  return { current, exiting, phase, push, pop, replace };
}
