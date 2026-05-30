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

async function request<T>(url: string, init?: RequestInit): Promise<T | null> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, (body as Record<string, string>).detail ?? `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}


export const API = {
  async getConfig(): Promise<ConfigData | null> {
    try {
      return await request<ConfigData>('/api/webapp-admin/config');
    } catch {
      return null;
    }
  },

  async getSchema(): Promise<Schemas | null> {
    try {
      return await request<Schemas>('/api/webapp-admin/config/schema');
    } catch {
      return null;
    }
  },

  async saveScope(
    scope: Scope,
    data: Record<string, unknown>,
  ): Promise<{ status: string } | null> {
    try {
      return await request<{ status: string }>(`/api/webapp-admin/config/${scope}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
    } catch {
      return null;
    }
  },

  async getServiceStatus(): Promise<ServiceStatuses | null> {
    try {
      return await request<ServiceStatuses>('/api/webapp-admin/services/status');
    } catch {
      return null;
    }
  },

  async controlService(
    service: Scope,
    action: 'start' | 'stop' | 'restart',
  ): Promise<{ status: string } | null> {
    try {
      return await request<{ status: string }>(
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
      return await request<{ lines: string[] }>(
        `/api/webapp-admin/services/${service}/logs`,
      );
    } catch {
      return null;
    }
  },

  async getDriveStatus(): Promise<DriveStatus | null> {
    try {
      return await request<DriveStatus>('/api/webapp-admin/drive/status');
    } catch {
      return null;
    }
  },

  async startDriveConnect(): Promise<{ auth_url: string } | null> {
    try {
      return await request<{ auth_url: string }>('/api/webapp-admin/drive/connect/start', {
        method: 'POST',
      });
    } catch {
      return null;
    }
  },

  async disconnectDrive(): Promise<{ status: string } | null> {
    try {
      return await request<{ status: string }>('/api/webapp-admin/drive/token', {
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
      const url = params ? `/api/webapp-admin/jenkinsfile?${params}` : '/api/webapp-admin/jenkinsfile';
      return await request<JenkinsfileResult>(url);
    } catch {
      return null;
    }
  },

  async getExportEnv(): Promise<ExportEnvResult | null> {
    try {
      return await request<ExportEnvResult>('/api/webapp-admin/export/env');
    } catch {
      return null;
    }
  },

  async downloadTarball(): Promise<boolean> {
    try {
      const res = await fetch('/api/webapp-admin/export/tarball');
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
      return await request<ImportResult>('/api/webapp-admin/import/tarball', {
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
      return await request<VpnStatus>('/api/webapp-admin/services/agent/vpn/status');
    } catch {
      return null;
    }
  },

  async vpnUpload(file: File): Promise<{ status: string } | null> {
    try {
      const form = new FormData();
      form.append('file', file);
      return await request<{ status: string }>('/api/webapp-admin/services/agent/vpn/upload', {
        method: 'POST',
        body: form,
      });
    } catch {
      return null;
    }
  },

  async vpnDelete(): Promise<{ status: string } | null> {
    try {
      return await request<{ status: string }>('/api/webapp-admin/services/agent/vpn/upload', {
        method: 'DELETE',
      });
    } catch {
      return null;
    }
  },

  async vpnConnect(): Promise<{ status: string } | null> {
    try {
      return await request<{ status: string }>('/api/webapp-admin/services/agent/vpn/connect', {
        method: 'POST',
      });
    } catch {
      return null;
    }
  },

  async vpnDisconnect(): Promise<{ status: string } | null> {
    try {
      return await request<{ status: string }>('/api/webapp-admin/services/agent/vpn/disconnect', {
        method: 'POST',
      });
    } catch {
      return null;
    }
  },
};
