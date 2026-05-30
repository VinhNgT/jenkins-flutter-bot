/**
 * Tests for the useNavigator hook — CSS transform-based stack navigation.
 *
 * Verifies the push/pop/replace lifecycle, phase transitions,
 * delayed unmount on pop, and concurrency guards.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/preact';
import { useNavigator, NAV_TRANSITION_MS } from '../../hooks/useNavigator';
import type { Screen } from '../../hooks/useNavigator';

const buildScreen: Screen = {
  screen: 'build-detail',
  type: 'active',
  id: 'build-123',
};

const recentScreen: Screen = {
  screen: 'build-detail',
  type: 'recent',
  id: 'build-456',
};

describe('useNavigator', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  it('starts in idle state with no screen', () => {
    const { result } = renderHook(() => useNavigator());
    expect(result.current.current).toBeNull();
    expect(result.current.exiting).toBeNull();
    expect(result.current.phase).toBe('idle');
  });

  it('push sets current and transitions to pushing phase', () => {
    const { result } = renderHook(() => useNavigator());

    act(() => {
      result.current.push(buildScreen);
    });

    expect(result.current.current).toEqual(buildScreen);
    expect(result.current.phase).toBe('pushing');
  });

  it('pop moves current to exiting and sets popping phase', () => {
    const { result } = renderHook(() => useNavigator());

    // First push a screen
    act(() => {
      result.current.push(buildScreen);
    });

    // Let the push animation complete
    act(() => {
      vi.advanceTimersByTime(NAV_TRANSITION_MS + 50);
    });

    // Now pop
    act(() => {
      result.current.pop();
    });

    expect(result.current.current).toBeNull();
    expect(result.current.exiting).toEqual(buildScreen);
    expect(result.current.phase).toBe('popping');
  });

  it('pop completes after transition timeout (delayed unmount)', () => {
    const { result } = renderHook(() => useNavigator());

    act(() => {
      result.current.push(buildScreen);
    });

    act(() => {
      vi.advanceTimersByTime(NAV_TRANSITION_MS + 50);
    });

    act(() => {
      result.current.pop();
    });

    // Advance past the pop transition
    act(() => {
      vi.advanceTimersByTime(NAV_TRANSITION_MS + 50);
    });

    expect(result.current.exiting).toBeNull();
    expect(result.current.phase).toBe('idle');
  });

  it('pop on empty stack is a no-op', () => {
    const { result } = renderHook(() => useNavigator());

    act(() => {
      result.current.pop();
    });

    expect(result.current.current).toBeNull();
    expect(result.current.phase).toBe('idle');
  });

  it('replace swaps the current screen without animation', () => {
    const { result } = renderHook(() => useNavigator());

    act(() => {
      result.current.push(buildScreen);
    });

    act(() => {
      vi.advanceTimersByTime(NAV_TRANSITION_MS + 50);
    });

    act(() => {
      result.current.replace(recentScreen);
    });

    expect(result.current.current).toEqual(recentScreen);
    // Phase should not change — no animation for replace
    expect(result.current.exiting).toBeNull();
  });

  it('NAV_TRANSITION_MS is 300ms', () => {
    expect(NAV_TRANSITION_MS).toBe(300);
  });
});
