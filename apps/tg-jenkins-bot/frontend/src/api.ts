/**
 * Typed API client for the Web App backend endpoints.
 *
 * All functions pass the Telegram initData via the X-Telegram-Init-Data
 * header. Errors throw ApiError with the structured detail from the backend.
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

function authHeaders(initData: string): HeadersInit {
  return { 'X-Telegram-Init-Data': initData };
}

/** GET /api/webapp/config — Fetch app configuration. */
export async function fetchConfig(initData: string): Promise<AppConfig> {
  const res = await fetch('/api/webapp/config', {
    headers: authHeaders(initData),
  });
  return handleResponse<AppConfig>(res);
}

/** POST /api/webapp/trigger — Trigger a new build. Returns request_id. */
export async function triggerBuild(initData: string, branch: string, notify: boolean = true): Promise<string> {
  const res = await fetch('/api/webapp/trigger', {
    method: 'POST',
    headers: {
      ...authHeaders(initData),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ branch, notify }),
  });
  const data = await handleResponse<{ ok: boolean; request_id: string }>(res);
  return data.request_id;
}

/** POST /api/webapp/cancel — Cancel an active build. */
export async function cancelBuild(initData: string, requestId: string): Promise<void> {
  const res = await fetch('/api/webapp/cancel', {
    method: 'POST',
    headers: {
      ...authHeaders(initData),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ request_id: requestId }),
  });
  await handleResponse<{ ok: boolean }>(res);
}
