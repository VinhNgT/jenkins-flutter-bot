/**
 * EphemeralBanner — Informational banner when file-manager uses ephemeral storage.
 */

import { HardDriveDownload } from 'lucide-preact';

export default function EphemeralBanner() {
  return (
    <div class="ephemeral-banner">
      <HardDriveDownload size={20} />
      <div>
        <strong>Ephemeral Storage Mode</strong>
        <p style={{ marginTop: '4px' }}>
          File storage is running in <strong>ephemeral mode</strong> — files are stored
          in memory and will be lost when the service restarts. This is intended for
          development and testing. To use persistent storage, set{' '}
          <code>STORAGE_BACKEND=google_drive</code>.
        </p>
      </div>
    </div>
  );
}
