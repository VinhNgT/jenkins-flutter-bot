/**
 * StorageBanner — Informational banner when file-manager uses ephemeral or log_only storage.
 */

import { HardDriveDownload, FileText } from 'lucide-preact';

export default function StorageBanner({ mode }: { mode: 'ephemeral' | 'log_only' }) {
  const isLogOnly = mode === 'log_only';

  return (
    <div class="ephemeral-banner">
      {isLogOnly ? <FileText size={20} /> : <HardDriveDownload size={20} />}
      <div>
        <strong>{isLogOnly ? 'Log-Only Storage Mode' : 'Ephemeral Storage Mode'}</strong>
        <p style={{ marginTop: '4px' }}>
          {isLogOnly ? (
            <>
              File storage is running in <strong>log-only mode</strong> — builds are logged
              but no files are saved. This is intended for testing without storage dependencies.
              To use persistent storage, set{' '}
              <code>STORAGE_BACKEND=google_drive</code>.
            </>
          ) : (
            <>
              File storage is running in <strong>ephemeral mode</strong> — files are stored
              in a temporary directory and will be lost when the service restarts. This is intended for
              development and testing. To use persistent storage, set{' '}
              <code>STORAGE_BACKEND=google_drive</code>.
            </>
          )}
        </p>
      </div>
    </div>
  );
}
