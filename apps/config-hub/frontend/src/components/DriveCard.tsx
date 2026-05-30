/**
 * DriveCard — Google Drive connection status and OAuth controls.
 *
 * In ephemeral mode this is hidden entirely (handled by parent).
 */

import { Cloud, LogOut, RotateCcw } from 'lucide-preact';
import { useEffect, useRef, useState } from 'preact/hooks';
import { API } from '../api';
import { useToast } from '../context/ToastContext';
import type { DriveStatus } from '../types';
import { Dialog } from 'tg-ui-preact';


interface DriveCardProps {
  driveStatus: DriveStatus | null;
  onRefresh: () => void;
}

export default function DriveCard({ driveStatus, onRefresh }: DriveCardProps) {
  const { showToast } = useToast();
  const [busy, setBusy] = useState(false);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const popupRef = useRef<Window | null>(null);
  const completedRef = useRef(false);
  const pollRef = useRef<any>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
      }
    };
  }, []);

  if (!driveStatus) {
    return (
      <div class="card" id="drive-connection">
        <h2>Google Drive Connection</h2>
        <p class="text-muted">Unable to check Drive status.</p>
      </div>
    );
  }

  const { connected, configured } = driveStatus;

  let statusText: string;
  let statusClass = '';
  if (!configured) {
    statusText = 'OAuth credentials not configured. Enter your Client ID and Secret above, then save.';
  } else if (connected) {
    statusText = 'Connected';
    statusClass = 'text-success';
  } else {
    statusText = 'Not connected. Click "Connect Google Drive" to authorize.';
  }

  async function startOAuthFlow() {
    setBusy(true);
    const result = await API.startDriveConnect();
    if (!result?.auth_url) {
      setBusy(false);
      return;
    }

    completedRef.current = false;
    dialogRef.current?.showModal();

    const popup = window.open(result.auth_url, '_blank');
    setBusy(false);

    if (!popup) {
      dialogRef.current?.close();
      showToast('Popup was blocked. Please allow popups for this site.', 'error');
      return;
    }

    popupRef.current = popup;

    if (pollRef.current) {
      clearInterval(pollRef.current);
    }

    // Poll for popup close
    pollRef.current = setInterval(() => {
      if (popup.closed) {
        if (pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
        if (!completedRef.current) {
          dialogRef.current?.close();
          onRefresh();
        }
      }
    }, 500);
  }

  async function disconnect() {
    setBusy(true);
    const result = await API.disconnectDrive();
    setBusy(false);
    if (result) {
      showToast('Google Drive disconnected', 'info');
      onRefresh();
    }
  }

  function handleCancel() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    popupRef.current?.close();
    dialogRef.current?.close();
    onRefresh();
  }

  // OAuth callback listener (set up once in App.tsx via window.addEventListener)
  // is handled at the app level — the dialog close + refresh happens there.

  return (
    <>
      <div class="card" id="drive-connection">
        <h2>Google Drive Connection</h2>
        <p class="text-muted" id="drive-status-detail">
          {statusClass ? <span class={statusClass}>{statusText}</span> : statusText}
          {connected && driveStatus.token_path && ` — Token: ${driveStatus.token_path}`}
        </p>
        <div class="form-actions" style={{ borderTop: 'none', paddingTop: 'var(--space-sm)' }}>
          <button
            class="btn btn-accent btn-sm"
            disabled={busy || !configured}
            onClick={startOAuthFlow}
          >
            {connected ? (
              <><RotateCcw class="icon" size={12} />Change Account</>
            ) : (
              <><Cloud class="icon" size={12} />Connect Google Drive</>
            )}
          </button>
          <button
            class="btn btn-danger btn-sm"
            disabled={busy || !connected}
            onClick={disconnect}
          >
            <LogOut class="icon" size={12} />
            Disconnect
          </button>
        </div>
      </div>

      {/* OAuth pending dialog */}
      <Dialog
        dialogRef={dialogRef}
        className="oauth-dialog"
        onCancel={(e) => {
          e.preventDefault();
        }}
      >
        <div class="dialog-icon">
          <Cloud size={40} />
        </div>
        <h2 class="dialog-title">Waiting for Google Authorization</h2>
        <p class="dialog-msg">
          Complete the sign-in process in the Google tab that just opened.
          This dialog will close automatically when authorization is complete.
        </p>
        <div class="dialog-status">
          <span class="spinner" />
          Waiting for callback…
        </div>
        <div class="dialog-actions">
          <button
            class="btn btn-secondary"
            onClick={handleCancel}
          >
            Cancel
          </button>
        </div>
      </Dialog>
    </>
  );
}

/**
 * Handle OAuth completion event from the oauth_callback.html postMessage.
 * Call this from the App level to close the dialog and refresh.
 */
export function handleOAuthComplete(
  event: MessageEvent,
  dialogRef: HTMLDialogElement | null,
  completedRef: { current: boolean },
  showToast: (msg: string, type: 'success' | 'error') => void,
  onRefresh: () => void,
) {
  if (event.origin !== window.location.origin) return;
  const data = event.data as { type?: string; success?: boolean; message?: string };
  if (data.type !== 'drive-oauth-complete') return;

  completedRef.current = true;
  dialogRef?.close();
  showToast(data.message ?? 'Authorization complete', data.success ? 'success' : 'error');
  onRefresh();
}
