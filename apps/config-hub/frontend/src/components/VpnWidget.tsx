/**
 * VpnWidget — OpenVPN configuration file management for the agent.
 *
 * Displays upload status, allows selecting/replacing/removing .ovpn files,
 * and provides VPN connect/disconnect controls.
 *
 * Uses a pending file pattern: the selected file is stored in component
 * state until the parent form is saved, at which point the file is
 * uploaded as part of the agent config save.
 */

import { useCallback, useEffect, useState } from 'preact/hooks';
import { useToast } from '../context/ToastContext';

interface VpnStatus {
  uploaded: boolean;
  connected: boolean;
  size: number;
}

interface VpnWidgetProps {
  /** Callback to signal the parent SchemaForm that a VPN file is pending upload. */
  onPendingFileChange?: (file: File | null) => void;
}

export default function VpnWidget({ onPendingFileChange }: VpnWidgetProps) {
  const { showToast } = useToast();
  const [status, setStatus] = useState<VpnStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);

  const refreshStatus = useCallback(async () => {
    try {
      const res = await fetch('/api/services/agent/vpn/status');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as VpnStatus;
      setStatus(data);
    } catch {
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshStatus();
  }, [refreshStatus]);

  // Expose pending file to parent via window for the save handler
  useEffect(() => {
    (window as unknown as Record<string, unknown>).pendingVpnFile = pendingFile;
    onPendingFileChange?.(pendingFile);
  }, [pendingFile, onPendingFileChange]);

  // Also expose refresh function globally for the save handler
  useEffect(() => {
    (window as unknown as Record<string, unknown>).refreshVpnWidgetStatus = refreshStatus;
  }, [refreshStatus]);

  function handleFileSelect(file: File) {
    if (!file.name.endsWith('.ovpn')) {
      showToast('Please upload a valid .ovpn file', 'error');
      return;
    }
    setPendingFile(file);
  }

  async function handleConnect() {
    setBusy(true);
    try {
      const res = await fetch('/api/services/agent/vpn/connect', { method: 'POST' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      showToast('VPN connected', 'success');
      await refreshStatus();
    } catch (err) {
      showToast(`Failed to connect VPN: ${(err as Error).message}`, 'error');
    } finally {
      setBusy(false);
    }
  }

  async function handleDisconnect() {
    setBusy(true);
    try {
      const res = await fetch('/api/services/agent/vpn/disconnect', { method: 'POST' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      showToast('VPN disconnected', 'info');
      await refreshStatus();
    } catch (err) {
      showToast(`Failed to disconnect VPN: ${(err as Error).message}`, 'error');
    } finally {
      setBusy(false);
    }
  }

  async function handleRemove() {
    if (!confirm('Remove the uploaded OpenVPN configuration file? This will stop VPN builds.')) return;
    setBusy(true);
    try {
      const res = await fetch('/api/services/agent/vpn/upload', { method: 'DELETE' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      showToast('OpenVPN configuration file removed', 'info');
      await refreshStatus();
    } catch (err) {
      showToast(`Failed to delete config: ${(err as Error).message}`, 'error');
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <div class="vpn-upload-container">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--tg-color-hint)', fontSize: '13px' }}>
          <span class="spinner" />
          Loading OpenVPN configuration status…
        </div>
      </div>
    );
  }

  if (!status) {
    return (
      <div class="vpn-upload-container">
        <div style={{ color: 'var(--tg-color-destructive)', fontSize: '13px' }}>
          Failed to load VPN status.{' '}
          <button class="btn btn-sm btn-secondary" onClick={refreshStatus}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div class="vpn-upload-container">
      <h4 style={{ margin: '0 0 0.75rem 0', fontSize: '14px', fontWeight: 600 }}>
        OpenVPN Config File (.ovpn)
      </h4>

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '1rem',
          padding: '1rem',
          borderRadius: 'var(--border-radius-card)',
          backgroundColor: 'rgba(255,255,255,0.03)',
          border: '1px solid var(--tg-color-separator)',
        }}
      >
        {/* Pending file state */}
        {pendingFile ? (
          <>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 500, color: 'var(--tg-color-warning)' }}>
                ⚡ Ready to Upload
                <span style={{
                  fontSize: '12px', padding: '2px 6px', borderRadius: '4px',
                  backgroundColor: 'rgba(224, 168, 48, 0.15)', color: 'var(--tg-color-warning)',
                  border: '1px solid rgba(224, 168, 48, 0.3)', fontWeight: 600,
                }}>
                  Pending Save
                </span>
              </div>
              <span style={{ fontSize: '13px', color: 'var(--tg-color-hint)' }}>
                {pendingFile.name} ({(pendingFile.size / 1024).toFixed(2)} KB)
                {status.uploaded && ' — will replace existing file'}
              </span>
            </div>
            <button
              class="btn btn-sm btn-secondary"
              onClick={() => setPendingFile(null)}
            >
              Cancel selection
            </button>
          </>
        ) : status.uploaded ? (
          /* Configured state */
          <>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 500, color: 'var(--tg-color-success)' }}>
                ✓ Configured
                {status.connected && (
                  <span style={{
                    fontSize: '12px', padding: '2px 6px', borderRadius: '4px',
                    backgroundColor: 'rgba(49, 181, 69, 0.15)', color: 'var(--tg-color-success)',
                    border: '1px solid rgba(49, 181, 69, 0.3)', fontWeight: 600,
                  }}>
                    Active Build Connection
                  </span>
                )}
              </div>
              <span style={{ fontSize: '13px', color: 'var(--tg-color-hint)' }}>
                .ovpn file uploaded ({(status.size / 1024).toFixed(2)} KB)
              </span>
            </div>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              {status.connected ? (
                <button
                  class="btn btn-sm btn-danger"
                  disabled={busy}
                  onClick={handleDisconnect}
                >
                  Disconnect VPN
                </button>
              ) : (
                <button
                  class="btn btn-sm btn-secondary"
                  style={{ borderColor: 'rgba(224, 168, 48, 0.3)', color: 'var(--tg-color-warning)' }}
                  disabled={busy}
                  onClick={handleConnect}
                >
                  Connect VPN
                </button>
              )}
              <label class="btn btn-sm btn-secondary" style={{ cursor: 'pointer', margin: 0 }}>
                Replace file…
                <input
                  type="file"
                  accept=".ovpn"
                  style={{ display: 'none' }}
                  onChange={(e) => {
                    const file = (e.target as HTMLInputElement).files?.[0];
                    if (file) handleFileSelect(file);
                  }}
                />
              </label>
              <button
                class="btn btn-sm btn-danger"
                disabled={busy}
                onClick={handleRemove}
              >
                Remove config
              </button>
            </div>
          </>
        ) : (
          /* Not configured state */
          <>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <div style={{ fontWeight: 500, color: 'var(--tg-color-hint)' }}>
                No configuration uploaded
              </div>
              <span style={{ fontSize: '13px', color: 'var(--tg-color-hint)' }}>
                Upload a .ovpn file to enable private network builds.
              </span>
            </div>
            <label class="btn btn-sm btn-secondary" style={{ cursor: 'pointer', margin: 0 }}>
              Choose file…
              <input
                type="file"
                accept=".ovpn"
                style={{ display: 'none' }}
                onChange={(e) => {
                  const file = (e.target as HTMLInputElement).files?.[0];
                  if (file) handleFileSelect(file);
                }}
              />
            </label>
          </>
        )}
      </div>
    </div>
  );
}
