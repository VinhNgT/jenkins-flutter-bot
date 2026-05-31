import { createContext } from 'preact';
import { useContext } from 'preact/hooks';

/**
 * Context that tracks whether the current screen is active and visible.
 * This is used to coordinate screen-level side effects (like physical back buttons,
 * primary main buttons) with navigation lifecycle transitions.
 */
export const ScreenActiveContext = createContext<boolean>(true);

/**
 * Returns whether the current screen is currently the active screen.
 */
export function useScreenActive(): boolean {
  return useContext(ScreenActiveContext);
}
