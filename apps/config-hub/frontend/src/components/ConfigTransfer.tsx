/**
 * ConfigTransfer — Export preview, tarball download, and tarball import.
 *
 * Supports generating env file previews per-scope, downloading a config
 * tarball, and importing a tarball with drag-and-drop.
 */

import { Download, Upload, Copy, FileCode, CheckCircle, XCircle, SkipForward, AlertTriangle } from 'lucide-preact';
import { useCallback, useRef, useState } from 'preact/hooks';
import { API } from '../api';
import { useToast } from '../context/ToastContext';
import type { ExportEnvResult } from '../types';
import { Scaffold, Button, TextArea } from 'tg-ui-preact';

interface ImportResult {
  applied?: string[];
  skipped_empty?: string[];
  unrecognized?: string[];
  parse_errors?: string[];
  warnings?: string[];
}

interface ConfigTransferProps {
  isActive: boolean;
  onBack: () => void;
}

export default function ConfigTransfer({ onBack }: ConfigTransferProps) {
  const { showToast } = useToast();

  // Export state
  const [exportData, setExportData] = useState<ExportEnvResult | null>(null);
  const [generating, setGenerating] = useState(false);
  const [downloading, setDownloading] = useState(false);

  // Import state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);
  const [importResults, setImportResults] = useState<ImportResult | null>(null);
  const [dragover, setDragover] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const getTabContent = useCallback(
    () => {
      if (!exportData) return '';
      return exportData.compose_env ?? '';
    },
    [exportData],
  );

  async function handleGenerate() {
    setGenerating(true);
    const result = await API.getExportEnv();
    setGenerating(false);

    if (result) {
      setExportData(result);
    }
  }

  async function handleDownload() {
    setDownloading(true);
    await API.downloadTarball();
    setDownloading(false);

  }

  async function handleCopy() {
    const text = getTabContent();
    try {
      await navigator.clipboard.writeText(text);
      showToast('Copied to clipboard', 'success');
    } catch {
      showToast('Press Ctrl+C to copy', 'info');
    }
  }

  function handleFileSelect(file: File) {
    setSelectedFile(file);
    setImportResults(null);
  }

  async function handleImport() {
    if (!selectedFile) return;
    setImporting(true);
    const result = (await API.importTarball(selectedFile)) as unknown as ImportResult | null;
    setImporting(false);

    if (result) {
      setImportResults(result);
      const applied = result.applied?.length ?? 0;
      showToast(
        `Import complete — ${applied} field(s) applied`,
        applied ? 'success' : 'info',
      );
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  return (
    <Scaffold
      title="Config Transfer"
      subtitle="Export your configuration as environment files for production deployment, or import a previously exported config tarball."
      onBack={onBack}
    >

      {/* ── Export Card ──────────────────────────────────────────── */}
      <div className="card">
        <h3>Export Configuration</h3>
        <p className="field-desc">
          Export your config parameters into a standard <code>compose.env</code> preview, or download a complete backup archive.
        </p>
        <div className="form-actions" style={{ borderTop: 'none', marginTop: '0', paddingTop: '0', gap: 'var(--space-sm)' }}>
          <Button
            variant="primary"
            disabled={generating}
            loading={generating}
            onClick={handleGenerate}
            style={{ flex: 1 }}
          >
            <FileCode className="icon" size={14} />
            Preview compose.env
          </Button>
          <Button
            variant="outline"
            disabled={downloading}
            loading={downloading}
            onClick={handleDownload}
            style={{ flex: 1 }}
          >
            <Download className="icon" size={14} />
            Download Tarball
          </Button>
        </div>
      </div>

      {exportData && (
        <div style={{ marginTop: 'var(--space-md)' }}>
          {exportData.warnings?.length ? (
            <div className="config-error-callout" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-xxs)' }}>
              {exportData.warnings.map((w, i) => (
                <p key={i} style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 'var(--space-xs)' }}>
                  <AlertTriangle size={12} style={{ flexShrink: 0 }} /> {w}
                </p>
              ))}
            </div>
          ) : null}

          <div className="export-tabs">
            <span style={{ fontSize: 'var(--font-size-md)', fontWeight: 500, padding: 'var(--space-xs) calc(var(--space-sm) + var(--space-xs))', color: 'var(--tg-color-text)' }}>
              compose.env
            </span>
            <button
              className="btn btn-sm btn-secondary"
              style={{ marginLeft: 'auto', marginBottom: 'var(--space-xs)' }}
              onClick={handleCopy}
            >
              <Copy className="icon" size={12} />
              Copy
            </button>
          </div>

          <TextArea
            className="export-output"
            value={getTabContent()}
            readOnly
            rows={12}
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 'var(--font-size-sm)',
              background: '#0d1117',
              color: '#c9d1d9',
              padding: '12px 16px',
            }}
          />
        </div>
      )}

      {/* ── Import Card ─────────────────────────────────────────── */}
      <div className="card" style={{ marginTop: 'var(--space-md)' }}>
        <h3>Import Configuration</h3>
        <p className="field-desc">
          Upload a previously generated <code>.tar.gz</code> archive to restore and apply all service configuration properties.
        </p>

        <div
          className={`import-zone${dragover ? ' dragover' : ''}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragover(true);
          }}
          onDragLeave={() => setDragover(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragover(false);
            const file = e.dataTransfer?.files[0];
            if (file) handleFileSelect(file);
          }}
        >
          <p>
            <Upload size={24} style={{ opacity: 0.5 }} />
          </p>
          <p>
            Drag and drop a <code>.tar.gz</code> config archive here, or{' '}
            <a
              onClick={(e) => {
                e.preventDefault();
                fileInputRef.current?.click();
              }}
            >
              browse
            </a>
          </p>
          {selectedFile && (
            <p style={{ fontWeight: 600, color: 'var(--tg-color-text)' }}>
              {selectedFile.name}
            </p>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept=".tar.gz,.tgz"
            hidden
            onChange={(e) => {
              const file = (e.target as HTMLInputElement).files?.[0];
              if (file) handleFileSelect(file);
            }}
          />
        </div>

        <div className="form-actions" style={{ borderTop: 'none', marginTop: '0', paddingTop: '0' }}>
          <Button
            variant="primary"
            disabled={importing || !selectedFile}
            loading={importing}
            onClick={handleImport}
          >
            <Upload className="icon" size={14} />
            Import
          </Button>
        </div>
      </div>

      {/* Import results */}
      {importResults && (
        <div class="import-results" style={{ marginTop: 'var(--space-md)' }}>
          {importResults.applied?.length ? (
            <div class="config-error-callout" style={{ color: 'var(--tg-color-success)', background: 'rgba(49, 181, 69, 0.08)', border: '1px solid rgba(49, 181, 69, 0.25)' }}>
              <h4 style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-xs)', margin: '0 0 var(--space-xs)', fontSize: 'var(--font-size-md)' }}>
                <CheckCircle size={14} /> Applied ({importResults.applied.length})
              </h4>
              <ul style={{ margin: 0, paddingLeft: 'var(--space-md)', fontSize: 'var(--font-size-sm)' }}>
                {importResults.applied.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {importResults.skipped_empty?.length ? (
            <div class="config-error-callout" style={{ color: 'var(--tg-color-hint)', background: 'rgba(128, 128, 128, 0.08)', border: '1px solid rgba(128, 128, 128, 0.25)', marginTop: 'var(--space-sm)' }}>
              <h4 style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-xs)', margin: '0 0 var(--space-xs)', fontSize: 'var(--font-size-md)' }}>
                <SkipForward size={14} /> Skipped ({importResults.skipped_empty.length})
              </h4>
              <ul style={{ margin: 0, paddingLeft: 'var(--space-md)', fontSize: 'var(--font-size-sm)' }}>
                {importResults.skipped_empty.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {importResults.unrecognized?.length ? (
            <div class="config-error-callout" style={{ marginTop: 'var(--space-sm)' }}>
              <h4 style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-xs)', margin: '0 0 var(--space-xs)', fontSize: 'var(--font-size-md)' }}>
                ❓ Unrecognized ({importResults.unrecognized.length})
              </h4>
              <ul style={{ margin: 0, paddingLeft: 'var(--space-md)', fontSize: 'var(--font-size-sm)' }}>
                {importResults.unrecognized.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {importResults.parse_errors?.length ? (
            <div class="config-error-callout" style={{ color: 'var(--tg-color-destructive)', background: 'rgba(255, 59, 48, 0.08)', border: '1px solid rgba(255, 59, 48, 0.25)', marginTop: 'var(--space-sm)' }}>
              <h4 style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-xs)', margin: '0 0 var(--space-xs)', fontSize: 'var(--font-size-md)' }}>
                <XCircle size={14} /> Errors ({importResults.parse_errors.length})
              </h4>
              <ul style={{ margin: 0, paddingLeft: 'var(--space-md)', fontSize: 'var(--font-size-sm)' }}>
                {importResults.parse_errors.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {importResults.warnings?.length ? (
            <div class="config-error-callout" style={{ marginTop: 'var(--space-sm)' }}>
              <h4 style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-xs)', margin: '0 0 var(--space-xs)', fontSize: 'var(--font-size-md)' }}>
                <AlertTriangle size={14} /> Warnings ({importResults.warnings.length})
              </h4>
              <ul style={{ margin: 0, paddingLeft: 'var(--space-md)', fontSize: 'var(--font-size-sm)' }}>
                {importResults.warnings.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      )}
    </Scaffold>
  );
}
