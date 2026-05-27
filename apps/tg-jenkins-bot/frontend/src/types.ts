/**
 * Shared TypeScript interfaces mirroring backend Pydantic response models.
 */

/** A configured branch option (from BotSettings.branches). */
export interface Branch {
  label: string;
  ref: string;
}

/** An active build currently in progress. */
export interface ActiveBuild {
  request_id: string;
  label: string;
  ref: string;
  triggered_at: number;
  triggered_by: string;
  triggered_by_id: number;
}

/** A completed build from build history. */
export interface RecentBuild {
  request_id: string;
  branch: string;
  label?: string;
  commit_hash: string | null;
  result: string;
  triggered_at: number;
  completed_at: number;
  download_url: string | null;
  file_size: number;
}

/** GET /api/webapp/config response. */
export interface AppConfig {
  app_name: string;
  app_version: string;
  branches: Branch[];
  active_builds: ActiveBuild[];
}

/**
 * Structured error detail from backend HTTPException responses.
 * Used to render contextual error screens (private chat, unauthorized group).
 */
export interface ApiErrorDetail {
  error?: string;
  message?: string;
  chat_id?: number;
  bot_username?: string;
}
