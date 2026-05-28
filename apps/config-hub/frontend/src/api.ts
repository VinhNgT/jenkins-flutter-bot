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

async function request<T>(url: string, init?: RequestInit): Promise<T | null> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as Record<string, string>).detail ?? `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

function normalizeSchema(schema: Schemas | null): Schemas | null {
  if (!schema) return null;
  const normalized: Schemas = {} as Schemas;
  for (const [scope, scopeSchema] of Object.entries(schema)) {
    const fields = (scopeSchema.fields || []).map((f: any) => {
      const choices: [string, string][] = f.choices || [];
      
      let type = f.type || f.field_type || 'string';
      
      const isBoolChoices = choices.length === 2 && 
        choices.some(c => c[0] === 'true') && 
        choices.some(c => c[0] === 'false');
        
      if (isBoolChoices || type === 'boolean') {
        type = 'boolean';
      } else if (choices.length > 0 || f.field_type === 'select') {
        type = 'select';
      } else if (f.field_type === 'integer' || f.field_type === 'number') {
        type = 'integer';
      }
      
      let options = f.options;
      if (!options && choices.length > 0) {
        options = choices.map(c => c[0]);
      }
      
      return {
        ...f,
        type,
        options,
        choices,
      };
    });
    
    normalized[scope as Scope] = {
      ...scopeSchema,
      fields,
    };
  }
  return normalized;
}

export const API = {
  async getConfig(): Promise<ConfigData | null> {
    try {
      return await request<ConfigData>('/api/config');
    } catch {
      return null;
    }
  },

  async getSchema(): Promise<Schemas | null> {
    try {
      const data = await request<Schemas>('/api/config/schema');
      return normalizeSchema(data);
    } catch {
      return null;
    }
  },

  async saveScope(
    scope: Scope,
    data: Record<string, unknown>,
  ): Promise<{ status: string } | null> {
    try {
      return await request<{ status: string }>(`/api/config/${scope}`, {
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
      return await request<ServiceStatuses>('/api/services/status');
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
        `/api/services/${service}/${action}`,
        { method: 'POST' },
      );
    } catch {
      return null;
    }
  },

  async getDriveStatus(): Promise<DriveStatus | null> {
    try {
      return await request<DriveStatus>('/api/drive/status');
    } catch {
      return null;
    }
  },

  async startDriveConnect(): Promise<{ auth_url: string } | null> {
    try {
      return await request<{ auth_url: string }>('/api/drive/connect/start', {
        method: 'POST',
      });
    } catch {
      return null;
    }
  },

  async disconnectDrive(): Promise<{ status: string } | null> {
    try {
      return await request<{ status: string }>('/api/drive/token', {
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
      const url = params ? `/api/jenkinsfile?${params}` : '/api/jenkinsfile';
      return await request<JenkinsfileResult>(url);
    } catch {
      return null;
    }
  },

  async getExportEnv(): Promise<ExportEnvResult | null> {
    try {
      return await request<ExportEnvResult>('/api/export/env');
    } catch {
      return null;
    }
  },

  async downloadTarball(): Promise<boolean> {
    try {
      const res = await fetch('/api/export/tarball');
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
      return await request<ImportResult>('/api/import/tarball', {
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
      return await request<VpnStatus>('/api/services/agent/vpn/status');
    } catch {
      return null;
    }
  },

  async vpnUpload(file: File): Promise<{ status: string } | null> {
    try {
      const form = new FormData();
      form.append('file', file);
      return await request<{ status: string }>('/api/services/agent/vpn/upload', {
        method: 'POST',
        body: form,
      });
    } catch {
      return null;
    }
  },

  async vpnDelete(): Promise<{ status: string } | null> {
    try {
      return await request<{ status: string }>('/api/services/agent/vpn/upload', {
        method: 'DELETE',
      });
    } catch {
      return null;
    }
  },

  async vpnConnect(): Promise<{ status: string } | null> {
    try {
      return await request<{ status: string }>('/api/services/agent/vpn/connect', {
        method: 'POST',
      });
    } catch {
      return null;
    }
  },

  async vpnDisconnect(): Promise<{ status: string } | null> {
    try {
      return await request<{ status: string }>('/api/services/agent/vpn/disconnect', {
        method: 'POST',
      });
    } catch {
      return null;
    }
  },
};
