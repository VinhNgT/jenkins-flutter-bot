/** Shared TypeScript interfaces for the config-hub dashboard. */

/* ─── Schema Types ────────────────────────────────────────────── */

export interface SchemaField {
  key: string;
  label: string;
  description: string;
  help_html?: string;
  type: 'string' | 'integer' | 'boolean' | 'select';
  default: string | number | boolean | null;
  required: boolean;
  secret: boolean;
  group: string;
  full_width?: boolean;
  options?: string[];
  placeholder?: string;
  field_type?: string;
}

export interface Schema {
  title: string;
  description: string;
  fields: SchemaField[];
}

export type Scope = 'bot' | 'agent' | 'builds' | 'file_manager';

export type Schemas = Record<Scope, Schema>;

/* ─── Config Types ────────────────────────────────────────────── */

export interface ScopeConfig {
  values: Record<string, unknown>;
  secret_lengths: Record<string, number>;
}

export type ConfigData = Record<Scope, ScopeConfig>;

/* ─── Service Status ──────────────────────────────────────────── */

export type ServiceState =
  | 'running'
  | 'stopped'
  | 'needs-config'
  | 'offline'
  | 'loading';

export interface ServiceStatus {
  configured: boolean;
  running: boolean;
  last_error: string | null;
  config_error: string | null;
  started_at?: number;
  backend_type?: string;
}

export type ServiceStatuses = Record<Scope, ServiceStatus | null>;

/* ─── Drive / Storage ─────────────────────────────────────────── */

export interface DriveStatus {
  backend: 'google_drive' | 'ephemeral';
  connected: boolean;
  configured: boolean;
  token_path?: string;
  file_count?: number;
  total_size_bytes?: number;
}

/* ─── VPN ─────────────────────────────────────────────────────── */

export interface VpnStatus {
  uploaded: boolean;
  connected: boolean;
  size: number;
}

/* ─── Jenkinsfile ─────────────────────────────────────────────── */

export interface JenkinsfileResult {
  script_public: string;
  script_private: string;
  warnings: string[];
}

/* ─── Config Transfer ─────────────────────────────────────────── */

export interface ExportEnvResult {
  files: Record<string, string>;
  compose_vars: Record<string, string>;
  warnings: string[];
}

export interface ImportResult {
  status: string;
  scopes_updated: string[];
  errors: string[];
}

/* ─── SSE Events ──────────────────────────────────────────────── */

export interface SSEServiceEvent {
  type: 'status';
  data: ServiceStatuses;
}
