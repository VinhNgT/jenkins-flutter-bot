import type { ComponentChildren } from 'preact';
import type { NavPhase } from '../hooks/useNavigator';
import { ScreenActiveContext } from '../context/ScreenActiveContext';

interface NavigatorProps {
  /** The active transition phase ('idle', 'pushing', 'pushed', 'popping') */
  phase: NavPhase;
  /** The root screen which remains mounted at the bottom of the stack */
  mainScreen: ComponentChildren;
  /** The active detail screen pushed onto the stack, if any */
  detailScreen: ComponentChildren | null;
  /** The exiting screen kept alive for the duration of the pop slide transition */
  exitingScreen: ComponentChildren | null;
}

export function Navigator({
  phase,
  mainScreen,
  detailScreen,
  exitingScreen,
}: NavigatorProps) {
  const viewportClass = `nav-viewport nav-${phase}`;

  return (
    <div className={viewportClass}>
      {/* Main / Root Screen */}
      <div className="nav-screen nav-screen--main">
        <ScreenActiveContext.Provider value={detailScreen == null}>
          {mainScreen}
        </ScreenActiveContext.Provider>
      </div>

      {/* Detail Screen Overlay */}
      {detailScreen && (
        <div className="nav-screen nav-screen--detail">
          <ScreenActiveContext.Provider value={true}>
            {detailScreen}
          </ScreenActiveContext.Provider>
        </div>
      )}

      {/* Exiting Screen (Delayed Visual Unmount Overlay) */}
      {!detailScreen && exitingScreen && (
        <div className="nav-screen nav-screen--detail">
          <ScreenActiveContext.Provider value={false}>
            {exitingScreen}
          </ScreenActiveContext.Provider>
        </div>
      )}
    </div>
  );
}
