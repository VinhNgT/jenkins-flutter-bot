/**
 * Typed API client for the Web App backend endpoints.
 */

import type { AppConfig, ApiErrorDetail } from './types';

/** Structured API error preserving backend detail shape. */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string | ApiErrorDetail,
  ) {
    const msg = typeof detail === 'string' ? detail : detail.message ?? 'Request failed';
    super(msg);
    this.name = 'ApiError';
  }
}

/** Parse error response body into ApiError. */
async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail: string | ApiErrorDetail;
    try {
      const body = await response.json();
      detail = body.detail ?? body;
    } catch {
      detail = `HTTP ${response.status}`;
    }
    throw new ApiError(response.status, detail);
  }
  return response.json() as Promise<T>;
}

export function createAPI(initData: string) {
  function authHeaders(): HeadersInit {
    return { 'X-Telegram-Init-Data': initData };
  }

  return {
    /** GET /api/webapp/config — Fetch app configuration. */
    async fetchConfig(): Promise<AppConfig> {
      const res = await fetch('/api/webapp/config', {
        headers: authHeaders(),
      });
      return handleResponse<AppConfig>(res);
    },

    /** POST /api/webapp/trigger — Trigger a new build. Returns request_id. */
    async triggerBuild(branch: string, notify: boolean = true): Promise<string> {
      const res = await fetch('/api/webapp/trigger', {
        method: 'POST',
        headers: {
          ...authHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ branch, notify }),
      });
      const data = await handleResponse<{ ok: boolean; request_id: string }>(res);
      return data.request_id;
    },

    /** POST /api/webapp/cancel — Cancel an active build. */
    async cancelBuild(requestId: string): Promise<void> {
      const res = await fetch('/api/webapp/cancel', {
        method: 'POST',
        headers: {
          ...authHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ request_id: requestId }),
      });
      await handleResponse<{ ok: boolean }>(res);
    },
  };
}

export type WebAppAPI = ReturnType<typeof createAPI>;
