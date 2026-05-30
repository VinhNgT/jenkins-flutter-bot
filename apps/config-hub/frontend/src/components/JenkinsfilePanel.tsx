/**
 * JenkinsfilePanel — Jenkins pipeline script generator.
 *
 * Generates public and private repository Jenkinsfile scripts
 * with configurable options. Persists repo params in localStorage.
 */

import { FileCode, Copy, Info, ChevronLeft } from 'lucide-preact';
import { useEffect, useRef, useState } from 'preact/hooks';
import { API } from '../api';
import { useToast } from '../context/ToastContext';
import type { JenkinsfileResult } from '../types';
import { useTelegram } from '../context/TelegramContext';
import { useBackButton } from '../hooks/useBackButton';

interface JenkinsfilePanelProps {
  isActive: boolean;
  onBack: () => void;
}

export default function JenkinsfilePanel({ isActive, onBack }: JenkinsfilePanelProps) {
  const { isTelegram } = useTelegram();
  useBackButton(isActive, onBack);
  const { showToast } = useToast();
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<JenkinsfileResult | null>(null);
  const [activeTab, setActiveTab] = useState<'public' | 'private'>('public');

  // Options
  const [discardBuilds, setDiscardBuilds] = useState(false);
  const [cleanWorkspace, setCleanWorkspace] = useState(false);
  const [shallowClone, setShallowClone] = useState(false);

  // Repo params (persisted in localStorage)
  const repoUrlRef = useRef<HTMLInputElement>(null);
  const credentialsIdRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (repoUrlRef.current) {
      repoUrlRef.current.value = localStorage.getItem('jf_repo_url') ?? '';
    }
    if (credentialsIdRef.current) {
      credentialsIdRef.current.value = localStorage.getItem('jf_credentials_id') ?? '';
    }
  }, []);

  async function handleGenerate() {
    setGenerating(true);

    const repoUrl = repoUrlRef.current?.value.trim() ?? '';
    const credentialsId = credentialsIdRef.current?.value.trim() ?? '';

    // Persist to localStorage
    localStorage.setItem('jf_repo_url', repoUrl);
    localStorage.setItem('jf_credentials_id', credentialsId);

    const data = await API.getJenkinsfile({
      discard_builds: String(discardBuilds),
      clean_workspace: String(cleanWorkspace),
      shallow_clone: String(shallowClone),
      repo_url: repoUrl,
      credentials_id: credentialsId,
    });

    setGenerating(false);

    if (data) {
      setResult(data);
    }
  }

  async function copyToClipboard(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      showToast('Copied to clipboard', 'success');
    } catch {
      showToast('Press Ctrl+C to copy', 'info');
    }
  }

  const currentScript = activeTab === 'public'
    ? result?.script_public ?? ''
    : result?.script_private ?? '';

  // Determine warnings per tab
  const repoUrlWarning = result?.warnings?.find((w) => w.includes('Repository URL'));
  const credentialsWarning = result?.warnings?.find((w) => w.includes('Repo Credentials ID'));

  return (
    <div class="container">
      {!isTelegram && (
        <header>
          <button class="back-button" onClick={onBack}>
            <ChevronLeft size={20} />
            Back
          </button>
        </header>
      )}

      <h2 class="panel-title">Pipeline Generator</h2>
      <p class="panel-desc">
        Generate ready-to-use Jenkinsfile pipeline scripts based on your current
        configuration. Supports both public and private repository setups.
      </p>

      {/* Repository Settings */}
      <div class="card">
        <h3>Repository Settings</h3>
        <div class="form-grid">
          <div class="field">
            <label>Repository URL</label>
            <span class="field-desc">
              Git repository URL for the Flutter project.
            </span>
            <input
              type="text"
              class="form-input"
              ref={repoUrlRef}
              placeholder="https://github.com/user/repo.git"
              onInput={(e) => localStorage.setItem('jf_repo_url', (e.target as HTMLInputElement).value.trim())}
            />
          </div>
          <div class="field">
            <label>Credentials ID (Private Repos)</label>
            <span class="field-desc">
              Jenkins credential ID for private repository access. Only used in the private repo script.
            </span>
            <input
              type="text"
              class="form-input"
              ref={credentialsIdRef}
              placeholder="my-git-credentials"
              onInput={(e) => localStorage.setItem('jf_credentials_id', (e.target as HTMLInputElement).value.trim())}
            />
          </div>
        </div>
      </div>

      {/* Options */}
      <div class="card" style={{ marginTop: 'var(--space-md)' }}>
        <h3>Pipeline Options</h3>
        <div class="form-grid">
          <div 
            class="switch-row"
            onClick={() => setDiscardBuilds(!discardBuilds)}
          >
            <div class="switch-text-group">
              <span class="form-toggle-label">Discard old builds</span>
              <span class="form-hint">Automatically discard old build logs and keep only the last 5 builds.</span>
            </div>
            <div class={`tg-toggle-track${discardBuilds ? ' tg-toggle-on' : ''}`}>
              <div class="tg-toggle-thumb" />
            </div>
          </div>
          <div 
            class="switch-row"
            onClick={() => setCleanWorkspace(!cleanWorkspace)}
          >
            <div class="switch-text-group">
              <span class="form-toggle-label">Clean workspace before build</span>
              <span class="form-hint">Wipe the Jenkins workspace folder clean before checking out source code.</span>
            </div>
            <div class={`tg-toggle-track${cleanWorkspace ? ' tg-toggle-on' : ''}`}>
              <div class="tg-toggle-thumb" />
            </div>
          </div>
          <div 
            class="switch-row"
            onClick={() => setShallowClone(!shallowClone)}
          >
            <div class="switch-text-group">
              <span class="form-toggle-label">Shallow clone</span>
              <span class="form-hint">Perform shallow git clone (depth 1) to speed up checkout and save bandwidth.</span>
            </div>
            <div class={`tg-toggle-track${shallowClone ? ' tg-toggle-on' : ''}`}>
              <div class="tg-toggle-thumb" />
            </div>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div class="form-actions">
        <button
          class="btn btn-accent"
          disabled={generating}
          onClick={handleGenerate}
        >
          <FileCode class="icon" size={14} />
          Generate Jenkinsfiles
        </button>
      </div>

      {/* Output */}
      {result && (
        <div style={{ marginTop: 'var(--space-md)' }}>
          {/* Tabs */}
          <div class="export-tabs">
            <button
              class={`export-tab${activeTab === 'public' ? ' active' : ''}`}
              onClick={() => setActiveTab('public')}
            >
              Public Repo
            </button>
            <button
              class={`export-tab${activeTab === 'private' ? ' active' : ''}`}
              onClick={() => setActiveTab('private')}
            >
              Private Repo
            </button>
            <button
              class="btn btn-sm btn-secondary"
              style={{ marginLeft: 'auto', marginBottom: 'var(--space-xs)' }}
              onClick={() => copyToClipboard(currentScript)}
            >
              <Copy class="icon" size={12} />
              Copy
            </button>
          </div>

          {/* Warning notices */}
          {repoUrlWarning && (
            <div class="config-error-callout" style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-sm)' }}>
              <Info size={14} style={{ flexShrink: 0 }} />
              <span>
                Using placeholder <code>&lt;YOUR_REPO_URL&gt;</code>. Configure
                your Git URL in the <strong>Repository Settings</strong> above for
                a ready-to-copy script.
              </span>
            </div>
          )}
          {activeTab === 'private' && credentialsWarning && (
            <div class="config-error-callout" style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-sm)' }}>
              <Info size={14} style={{ flexShrink: 0 }} />
              <span>
                Using placeholder <code>&lt;YOUR_CREDENTIALS_ID&gt;</code>.
                Configure your Credentials ID in the{' '}
                <strong>Repository Settings</strong> above.
              </span>
            </div>
          )}

          <textarea
            class="jenkinsfile-output"
            value={currentScript}
            readOnly
          />
        </div>
      )}
    </div>
  );
}
