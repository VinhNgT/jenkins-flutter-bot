/**
 * Tests for the useNavigator hook.
 *
 * Verifies the full push/pop/replace lifecycle including:
 * - Phase transitions (idle → pushing → pushed, pushed → popping → idle)
 * - Delayed unmount: exiting screen stays mounted during pop animation
 * - Guard against concurrent push/pop operations
 *
 * rAF in jsdom with fake timers needs explicit advancement via
 * vi.advanceTimersByTime(16) to tick one animation frame.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/preact';
import { useNavigator, NAV_TRANSITION_MS } from '../../hooks/useNavigator';
import type { Screen } from '../../hooks/useNavigator';

/** Advance enough to trigger two nested rAF callbacks + setTimeout. */
function flushPushAnimation() {
  // Each rAF fires after ~16ms. Two nested rAFs + the setTimeout guard.
  vi.advanceTimersByTime(16); // first rAF fires
  vi.advanceTimersByTime(16); // second rAF fires
  vi.advanceTimersByTime(NAV_TRANSITION_MS); // setTimeout completes
}

describe('useNavigator', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('starts in idle state with no screens', () => {
    const { result } = renderHook(() => useNavigator());
    expect(result.current.current).toBeNull();
    expect(result.current.exiting).toBeNull();
    expect(result.current.phase).toBe('idle');
  });

  it('push sets current screen and transitions through phases', () => {
    const { result } = renderHook(() => useNavigator());
    const screen: Screen = { screen: 'config', id: 'telegram' };

    act(() => {
      result.current.push(screen);
    });

    // After push: screen is mounted, phase is 'pushing'
    expect(result.current.current).toEqual(screen);
    expect(result.current.phase).toBe('pushing');

    // Advance through both rAF callbacks + transition timeout
    act(() => {
      flushPushAnimation();
    });

    // Phase should now be 'pushed' with the animation guard released
    expect(result.current.phase).toBe('pushed');
    expect(result.current.current).toEqual(screen);
  });

  it('pop slides out and removes screen after transition delay', () => {
    const { result } = renderHook(() => useNavigator());
    const screen: Screen = { screen: 'config', id: 'jenkins' };

    // Push and complete the animation
    act(() => {
      result.current.push(screen);
      flushPushAnimation();
    });

    expect(result.current.current).toEqual(screen);

    // Pop
    act(() => {
      result.current.pop();
    });

    // During animation: current is null, but exiting is still mounted
    expect(result.current.current).toBeNull();
    expect(result.current.exiting).toEqual(screen);
    expect(result.current.phase).toBe('popping');

    // After transition: exiting is unmounted, phase is idle
    act(() => {
      vi.advanceTimersByTime(NAV_TRANSITION_MS);
    });

    expect(result.current.exiting).toBeNull();
    expect(result.current.phase).toBe('idle');
  });

  it('pop does nothing when no screen is pushed', () => {
    const { result } = renderHook(() => useNavigator());

    act(() => {
      result.current.pop();
    });

    expect(result.current.current).toBeNull();
    expect(result.current.phase).toBe('idle');
  });

  it('replace updates screen data without animation', () => {
    const { result } = renderHook(() => useNavigator());
    const screen1: Screen = { screen: 'config', id: 'telegram' };
    const screen2: Screen = { screen: 'config', id: 'storage' };

    // Push initial screen and complete animation
    act(() => {
      result.current.push(screen1);
      flushPushAnimation();
    });

    // Replace
    act(() => {
      result.current.replace(screen2);
    });

    expect(result.current.current).toEqual(screen2);
    expect(result.current.phase).toBe('pushed');
  });

  it('blocks concurrent push during animation', () => {
    const { result } = renderHook(() => useNavigator());
    const screen1: Screen = { screen: 'config', id: 'telegram' };
    const screen2: Screen = { screen: 'tools' };

    act(() => {
      result.current.push(screen1);
    });

    // Try pushing again before animation completes — should be blocked
    act(() => {
      result.current.push(screen2);
    });

    expect(result.current.current).toEqual(screen1);
  });
});
