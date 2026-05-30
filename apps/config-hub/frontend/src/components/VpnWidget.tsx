/**
 * VpnWidget — OpenVPN configuration file management for the agent.
 *
 * Displays upload status, allows selecting/replacing/removing .ovpn files,
 * and provides VPN connect/disconnect controls.
 *
 * VPN file upload is immediate (not pending) — the file is uploaded directly
 * to the agent service when selected, independent of the config form save.
 */

import {
  FileUp,
  Loader2,
  PlugZap,
  RefreshCw,
  ShieldAlert,
  Trash2,
  Upload,
  Unplug,
} from 'lucide-preact';
import { useCallback, useEffect, useState } from 'preact/hooks';
import { API } from '../api';
import { useToast } from '../context/ToastContext';
import { useConfirm } from '../context/ConfirmDialog';
import { useTelegram } from '../context/TelegramContext';
import type { VpnStatus } from '../types';

export default function VpnWidget() {
  const { showToast } = useToast();
  const confirm = useConfirm();
  const { haptic } = useTelegram();
  const [status, setStatus] = useState<VpnStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const refreshStatus = useCallback(async () => {
    const result = await API.vpnStatus();
    setStatus(result);
    setLoading(false);
  }, []);

  useEffect(() => {
    refreshStatus();
  }, [refreshStatus]);

  async function handleFileSelect(file: File) {
    if (!file.name.endsWith('.ovpn')) {
      haptic.notification('error');
      showToast('Please upload a valid .ovpn file', 'error');
      return;
    }
    haptic.impact('medium');
    setBusy(true);
    const result = await API.vpnUpload(file);
    if (result) {
      showToast('Config uploaded', 'success');
      await refreshStatus();
    } else {
      showToast('Failed to upload OpenVPN configuration', 'error');
    }
    setBusy(false);
  }

  async function handleConnect() {
    haptic.impact('medium');
    setBusy(true);
    const result = await API.vpnConnect();
    if (result) {
      showToast('Connected', 'success');
      await refreshStatus();
    } else {
      showToast('Failed to connect VPN', 'error');
    }
    setBusy(false);
  }

  async function handleDisconnect() {
    haptic.impact('medium');
    setBusy(true);
    const result = await API.vpnDisconnect();
    if (result) {
      showToast('Disconnected', 'info');
      await refreshStatus();
    } else {
      showToast('Failed to disconnect VPN', 'error');
    }
    setBusy(false);
  }

  async function handleRemove() {
    const confirmed = await confirm({
      title: 'Remove VPN Configuration?',
      message:
        'This will delete the uploaded OpenVPN configuration file. VPN-dependent builds will fail until a new file is uploaded.',
      confirmLabel: 'Remove',
      danger: true,
    });
    if (!confirmed) return;
    haptic.impact('heavy');

    setBusy(true);
    const result = await API.vpnDelete();
    if (result) {
      showToast('Config removed', 'info');
      await refreshStatus();
    } else {
      showToast('Failed to delete configuration', 'error');
    }
    setBusy(false);
  }

  // ─── Loading State ───────────────────────────────────────────
  if (loading) {
    return (
      <div class="card" id="vpn-connection">
        <h2>OpenVPN Connection</h2>
        <div class="vpn-loading">
          <Loader2 class="icon spinner-icon" size={14} />
          Loading OpenVPN configuration status…
        </div>
      </div>
    );
  }

  // ─── Error State ─────────────────────────────────────────────
  if (!status) {
    return (
      <div class="card" id="vpn-connection">
        <h2>OpenVPN Connection</h2>
        <div class="vpn-error">
          <ShieldAlert class="icon" size={14} />
          Failed to load VPN status.
          <button class="btn btn-sm btn-secondary" onClick={refreshStatus}>
            <RefreshCw class="icon" size={12} />
            Retry
          </button>
        </div>
      </div>
    );
  }

  // ─── Configured State ────────────────────────────────────────
  return (
    <div class="card" id="vpn-connection">
      <h2>OpenVPN Connection</h2>

      <p class="text-muted" id="vpn-status-detail">
        {status.uploaded ? (
          <>
            <span class={status.connected ? 'text-success' : 'text-warning'}>
              {status.connected ? 'Connected' : 'Disconnected'}
            </span>
            {status.connected && (
              <span class="badge badge--running" style={{ marginLeft: 'var(--space-sm)' }}>Active Connection</span>
            )}
            {` — File uploaded (${(status.size / 1024).toFixed(2)} KB)`}
          </>
        ) : (
          <span class="text-muted">No configuration uploaded. Upload a .ovpn file to enable private network builds.</span>
        )}
      </p>

      <div class="form-actions" style={{ borderTop: 'none', paddingTop: 'var(--space-sm)' }}>
        {status.uploaded ? (
          <>
            {status.connected ? (
              <button
                class="btn btn-danger btn-sm"
                disabled={busy}
                onClick={handleDisconnect}
              >
                <Unplug class="icon" size={12} />
                Disconnect
              </button>
            ) : (
              <button
                class="btn btn-accent btn-sm"
                disabled={busy}
                onClick={handleConnect}
              >
                <PlugZap class="icon" size={12} />
                Connect
              </button>
            )}
            <label class="btn btn-secondary btn-sm vpn-file-label">
              <FileUp class="icon" size={12} />
              Replace file…
              <input
                type="file"
                accept=".ovpn"
                class="vpn-file-input"
                style={{ display: 'none' }}
                onChange={(e) => {
                  const file = (e.target as HTMLInputElement).files?.[0];
                  if (file) handleFileSelect(file);
                }}
              />
            </label>
            <button
              class="btn btn-danger btn-sm"
              disabled={busy}
              onClick={handleRemove}
            >
              <Trash2 class="icon" size={12} />
              Remove
            </button>
          </>
        ) : (
          <label class="btn btn-accent btn-sm vpn-file-label">
            <Upload class="icon" size={12} />
            Choose file…
            <input
              type="file"
              accept=".ovpn"
              class="vpn-file-input"
              style={{ display: 'none' }}
              onChange={(e) => {
                const file = (e.target as HTMLInputElement).files?.[0];
                if (file) handleFileSelect(file);
              }}
            />
          </label>
        )}
      </div>
    </div>
  );
}
