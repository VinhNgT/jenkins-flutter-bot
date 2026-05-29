/**
 * Shared utilities for the config-hub frontend.
 */

/** Possible health states for a service. */
export type HealthState = 'running' | 'stopped' | 'needs-config' | 'offline';

/** Derive a health state from a service status object. */
export function healthState(
  status: { configured: boolean; running: boolean } | null,
): HealthState {
  if (!status) return 'offline';
  if (!status.configured) return 'needs-config';
  if (!status.running) return 'stopped';
  return 'running';
}
