/**
 * Tests for the healthState utility function.
 *
 * Verifies all four health state derivations from service status objects.
 */

import { describe, it, expect } from 'vitest';
import { healthState } from '../utils';
import type { HealthState } from '../utils';

describe('healthState', () => {
  it('returns "offline" when status is null', () => {
    expect(healthState(null)).toBe('offline' satisfies HealthState);
  });

  it('returns "needs-config" when not configured', () => {
    expect(healthState({ configured: false, running: false })).toBe('needs-config');
  });

  it('returns "needs-config" when configured=false even if running=true', () => {
    // Edge case: shouldn't happen in practice, but configured takes priority
    expect(healthState({ configured: false, running: true })).toBe('needs-config');
  });

  it('returns "stopped" when configured but not running', () => {
    expect(healthState({ configured: true, running: false })).toBe('stopped');
  });

  it('returns "running" when configured and running', () => {
    expect(healthState({ configured: true, running: true })).toBe('running');
  });
});
