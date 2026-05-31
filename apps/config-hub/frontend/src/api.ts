/** Centralized API client — typed fetch wrappers for all config-hub endpoints. */

import type {
  ConfigData,
  DriveStatus,
  ExportEnvResult,
  ImportResult,
  JenkinsfileResult,
  Schemas,
  Scope,
  ServiceStatuses,
  VpnStatus,
} from './types';

/** Structured API error with HTTP status and server detail message. */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(`HTTP ${status}: ${detail}`);
    this.name = 'ApiError';
  }
}

async function request<T>(
  url: string,
  initData: string,
  init?: RequestInit,
): Promise<T | null> {
  const headers = new Headers(init?.headers);
  if (initData) {
    headers.set('X-Telegram-Init-Data', initData);
  }

  const res = await fetch(url, { ...init, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(
      res.status,
      (body as Record<string, string>).detail ?? `HTTP ${res.status}`,
    );
  }
  return (await res.json()) as T;
}

export function createAPI(initData: string) {
  const req = <T>(url: string, init?: RequestInit) =>
    request<T>(url, initData, init);

  return {
    async getConfig(): Promise<ConfigData | null> {
      try {
        return await req<ConfigData>('/api/webapp-admin/config');
      } catch {
        return null;
      }
    },

    async getSchema(): Promise<Schemas | null> {
      try {
        return await req<Schemas>('/api/webapp-admin/config/schema');
      } catch {
        return null;
      }
    },

    async saveScope(
      scope: Scope,
      data: Record<string, unknown>,
    ): Promise<{ status: string } | null> {
      try {
        return await req<{ status: string }>(
          `/api/webapp-admin/config/${scope}`,
          {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
          },
        );
      } catch {
        return null;
      }
    },

    async getServiceStatus(): Promise<ServiceStatuses | null> {
      try {
        return await req<ServiceStatuses>('/api/webapp-admin/services/status');
      } catch {
        return null;
      }
    },

    async controlService(
      service: Scope,
      action: 'start' | 'stop' | 'restart',
    ): Promise<{ status: string } | null> {
      try {
        return await req<{ status: string }>(
          `/api/webapp-admin/services/${service}/${action}`,
          { method: 'POST' },
        );
      } catch {
        return null;
      }
    },

    async getServiceLogs(
      service: Scope,
    ): Promise<{ lines: string[] } | null> {
      try {
        return await req<{ lines: string[] }>(
          `/api/webapp-admin/services/${service}/logs`,
        );
      } catch {
        return null;
      }
    },

    async getDriveStatus(): Promise<DriveStatus | null> {
      try {
        return await req<DriveStatus>('/api/webapp-admin/drive/status');
      } catch {
        return null;
      }
    },

    async startDriveConnect(): Promise<{ auth_url: string } | null> {
      try {
        return await req<{ auth_url: string }>(
          '/api/webapp-admin/drive/connect/start',
          {
            method: 'POST',
          },
        );
      } catch {
        return null;
      }
    },

    async disconnectDrive(): Promise<{ status: string } | null> {
      try {
        return await req<{ status: string }>('/api/webapp-admin/drive/token', {
          method: 'DELETE',
        });
      } catch {
        return null;
      }
    },

    async getJenkinsfile(
      opts: Record<string, string> = {},
    ): Promise<JenkinsfileResult | null> {
      try {
        const params = new URLSearchParams(opts).toString();
        const url = params
          ? `/api/webapp-admin/jenkinsfile?${params}`
          : '/api/webapp-admin/jenkinsfile';
        return await req<JenkinsfileResult>(url);
      } catch {
        return null;
      }
    },

    async getExportEnv(): Promise<ExportEnvResult | null> {
      try {
        return await req<ExportEnvResult>('/api/webapp-admin/export/env');
      } catch {
        return null;
      }
    },

    async downloadTarball(): Promise<boolean> {
      try {
        const res = await fetch('/api/webapp-admin/export/tarball', {
          headers: { 'X-Telegram-Init-Data': initData },
        });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(
            (body as Record<string, string>).detail ?? `HTTP ${res.status}`,
          );
        }
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'jfb-config.tar.gz';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        return true;
      } catch {
        return false;
      }
    },

    async importTarball(file: File): Promise<ImportResult | null> {
      try {
        const form = new FormData();
        form.append('file', file);
        return await req<ImportResult>('/api/webapp-admin/import/tarball', {
          method: 'POST',
          body: form,
        });
      } catch {
        return null;
      }
    },

    // ─── VPN ─────────────────────────────────────────────────────
    async vpnStatus(): Promise<VpnStatus | null> {
      try {
        return await req<VpnStatus>(
          '/api/webapp-admin/services/agent/vpn/status',
        );
      } catch {
        return null;
      }
    },

    async vpnUpload(file: File): Promise<{ status: string } | null> {
      try {
        const form = new FormData();
        form.append('file', file);
        return await req<{ status: string }>(
          '/api/webapp-admin/services/agent/vpn/upload',
          {
            method: 'POST',
            body: form,
          },
        );
      } catch {
        return null;
      }
    },

    async vpnDelete(): Promise<{ status: string } | null> {
      try {
        return await req<{ status: string }>(
          '/api/webapp-admin/services/agent/vpn/upload',
          {
            method: 'DELETE',
          },
        );
      } catch {
        return null;
      }
    },

    async vpnConnect(): Promise<{ status: string } | null> {
      try {
        return await req<{ status: string }>(
          '/api/webapp-admin/services/agent/vpn/connect',
          {
            method: 'POST',
          },
        );
      } catch {
        return null;
      }
    },

    async vpnDisconnect(): Promise<{ status: string } | null> {
      try {
        return await req<{ status: string }>(
          '/api/webapp-admin/services/agent/vpn/disconnect',
          {
            method: 'POST',
          },
        );
      } catch {
        return null;
      }
    },
  };
}

export type ConfigHubAPI = ReturnType<typeof createAPI>;
