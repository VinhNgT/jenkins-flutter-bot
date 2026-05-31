/**
 * Shared utility functions for the service-hub frontend.
 */

import type { ServiceStatus } from './types';

/** Derived health state from a service status object. */
export type HealthState = 'running' | 'needs-config' | 'stopped' | 'offline';

/** Derives the display health state from a service status. */
export function healthState(status: ServiceStatus | null): HealthState {
  if (!status) return 'offline';
  if (!status.configured) return 'needs-config';
  return status.running ? 'running' : 'stopped';
}
