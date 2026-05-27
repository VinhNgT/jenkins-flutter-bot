/**
 * JenkinsfilePanel — Jenkins pipeline script generator.
 *
 * Generates public and private repository Jenkinsfile scripts
 * with configurable options. Persists repo params in localStorage.
 */

import { FileCode, Copy } from 'lucide-preact';
import { useEffect, useRef, useState } from 'preact/hooks';
import { API } from '../api';
import { useToast } from '../context/ToastContext';
import type { JenkinsfileResult } from '../types';

export default function JenkinsfilePanel() {
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
      showToast('Jenkinsfiles generated', 'success');
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
    <div>
      <h2 class="panel-title">Jenkins Pipeline Generator</h2>
      <p class="panel-desc">
        Generate ready-to-use Jenkinsfile pipeline scripts based on your current
        configuration. Supports both public and private repository setups.
      </p>

      {/* Repository Settings */}
      <div class="card" style={{ marginBottom: '12px' }}>
        <h3>Repository Settings</h3>
        <div class="jf-input-group">
          <label>Repository URL</label>
          <input
            type="text"
            ref={repoUrlRef}
            placeholder="https://github.com/user/repo.git"
            onInput={(e) => localStorage.setItem('jf_repo_url', (e.target as HTMLInputElement).value.trim())}
          />
          <span class="help-text">
            Git repository URL for the Flutter project.
          </span>
        </div>
        <div class="jf-input-group">
          <label>Credentials ID (Private Repos)</label>
          <input
            type="text"
            ref={credentialsIdRef}
            placeholder="my-git-credentials"
            onInput={(e) => localStorage.setItem('jf_credentials_id', (e.target as HTMLInputElement).value.trim())}
          />
          <span class="help-text">
            Jenkins credential ID for private repository access. Only used in the private repo script.
          </span>
        </div>
      </div>

      {/* Options */}
      <div class="jenkinsfile-opts">
        <h3>Pipeline Options</h3>
        <label>
          <input
            type="checkbox"
            checked={discardBuilds}
            onChange={() => setDiscardBuilds(!discardBuilds)}
          />
          Discard old builds (keep last 5)
        </label>
        <label>
          <input
            type="checkbox"
            checked={cleanWorkspace}
            onChange={() => setCleanWorkspace(!cleanWorkspace)}
          />
          Clean workspace before build
        </label>
        <label>
          <input
            type="checkbox"
            checked={shallowClone}
            onChange={() => setShallowClone(!shallowClone)}
          />
          Shallow clone (depth 1)
        </label>
      </div>

      {/* Actions */}
      <div class="jenkinsfile-actions">
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
        <>
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
              style={{ marginLeft: 'auto', marginBottom: '4px' }}
              onClick={() => copyToClipboard(currentScript)}
            >
              <Copy class="icon" size={12} />
              Copy
            </button>
          </div>

          {/* Warning notices */}
          {repoUrlWarning && (
            <div class="jf-placeholder-notice">
              <span class="notice-icon">ℹ️</span>
              <span>
                Using placeholder <code>&lt;YOUR_REPO_URL&gt;</code>. Configure
                your Git URL in the <strong>Repository Settings</strong> above for
                a ready-to-copy script.
              </span>
            </div>
          )}
          {activeTab === 'private' && credentialsWarning && (
            <div class="jf-placeholder-notice">
              <span class="notice-icon">ℹ️</span>
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
        </>
      )}
    </div>
  );
}
