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

interface ImportResult {
  applied?: string[];
  skipped_empty?: string[];
  unrecognized?: string[];
  parse_errors?: string[];
  warnings?: string[];
}

export default function ConfigTransfer() {
  const { showToast } = useToast();

  // Export state
  const [exportData, setExportData] = useState<ExportEnvResult | null>(null);
  const [activeExportTab, setActiveExportTab] = useState('bot');
  const [generating, setGenerating] = useState(false);
  const [downloading, setDownloading] = useState(false);

  // Import state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);
  const [importResults, setImportResults] = useState<ImportResult | null>(null);
  const [dragover, setDragover] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const getTabContent = useCallback(
    (tab: string) => {
      if (!exportData) return '';
      if (tab === 'compose') {
        const bot = exportData.compose_vars?.bot ?? '';
        const agent = exportData.compose_vars?.agent ?? '';
        return bot + '\n' + agent;
      }
      return exportData.files?.[`${tab}.env`] ?? '';
    },
    [exportData],
  );

  async function handleGenerate() {
    setGenerating(true);
    const result = await API.getExportEnv();
    setGenerating(false);

    if (result) {
      setExportData(result);
      setActiveExportTab('bot');
      showToast('Config preview generated', 'success');
    }
  }

  async function handleDownload() {
    setDownloading(true);
    const ok = await API.downloadTarball();
    setDownloading(false);
    if (ok) showToast('Tarball downloaded', 'success');
  }

  async function handleCopy() {
    const text = getTabContent(activeExportTab);
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

  const EXPORT_TABS = [
    { id: 'bot', label: 'bot.env' },
    { id: 'agent', label: 'agent.env' },
    { id: 'file_manager', label: 'file_manager.env' },
    { id: 'compose', label: 'compose vars' },
  ];

  return (
    <div>
      <h2 class="panel-title">Config Transfer</h2>
      <p class="panel-desc">
        Export your configuration as environment files for production deployment,
        or import a previously exported config tarball.
      </p>

      {/* ── Export Section ──────────────────────────────────────────── */}
      <h3 class="panel-subtitle">Export</h3>

      <div class="export-actions">
        <button
          class="btn btn-accent"
          disabled={generating}
          onClick={handleGenerate}
        >
          <FileCode class="icon" size={14} />
          Preview .env Files
        </button>
        <button
          class="btn btn-secondary"
          disabled={downloading}
          onClick={handleDownload}
        >
          <Download class="icon" size={14} />
          Download Tarball
        </button>
      </div>

      {exportData && (
        <>
          {exportData.warnings?.length ? (
            <div class="export-warnings">
              {exportData.warnings.map((w, i) => (
                <p key={i}><AlertTriangle class="icon" size={12} /> {w}</p>
              ))}
            </div>
          ) : null}

          <div class="export-tabs">
            {EXPORT_TABS.map(({ id, label }) => (
              <button
                key={id}
                class={`export-tab${activeExportTab === id ? ' active' : ''}`}
                onClick={() => setActiveExportTab(id)}
              >
                {label}
              </button>
            ))}
            <button
              class="btn btn-sm btn-secondary"
              style={{ marginLeft: 'auto', marginBottom: '4px' }}
              onClick={handleCopy}
            >
              <Copy class="icon" size={12} />
              Copy
            </button>
          </div>

          <textarea
            class="export-output"
            value={getTabContent(activeExportTab)}
            readOnly
          />
        </>
      )}

      {/* ── Import Section ─────────────────────────────────────────── */}
      <h3 class="panel-subtitle">Import</h3>

      <div
        class={`import-zone${dragover ? ' dragover' : ''}`}
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

      <div class="form-actions" style={{ borderTop: 'none' }}>
        <button
          class="btn btn-accent"
          disabled={importing || !selectedFile}
          onClick={handleImport}
        >
          <Upload class="icon" size={14} />
          Import
        </button>
      </div>

      {/* Import results */}
      {importResults && (
        <div class="import-results">
          {importResults.applied?.length ? (
            <>
              <h4><CheckCircle class="icon" size={14} /> Applied ({importResults.applied.length})</h4>
              <ul>
                {importResults.applied.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </>
          ) : null}
          {importResults.skipped_empty?.length ? (
            <>
              <h4><SkipForward class="icon" size={14} /> Skipped ({importResults.skipped_empty.length})</h4>
              <ul>
                {importResults.skipped_empty.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </>
          ) : null}
          {importResults.unrecognized?.length ? (
            <>
              <h4>❓ Unrecognized ({importResults.unrecognized.length})</h4>
              <ul>
                {importResults.unrecognized.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </>
          ) : null}
          {importResults.parse_errors?.length ? (
            <>
              <h4><XCircle class="icon" size={14} /> Errors ({importResults.parse_errors.length})</h4>
              <ul>
                {importResults.parse_errors.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </>
          ) : null}
          {importResults.warnings?.length ? (
            <>
              <h4><AlertTriangle class="icon" size={14} /> Warnings ({importResults.warnings.length})</h4>
              <ul>
                {importResults.warnings.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </>
          ) : null}
        </div>
      )}
    </div>
  );
}
