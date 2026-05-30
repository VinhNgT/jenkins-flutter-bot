/**
 * App — Root application component.
 *
 * Manages global state: schemas, configs, service statuses, active section.
 * Orchestrates data fetching on mount and delegates to child components.
 *
 * UI sections map to backend scopes:
 *   services  → dashboard (all scopes)
 *   telegram  → bot scope
 *   jenkins   → agent + builds scopes
 *   storage   → file_manager scope
 *   tools     → jenkinsfile + config transfer
 */

import { useCallback, useEffect, useState } from 'preact/hooks';


/** Inline GitHub SVG — Lucide 1.x removed brand icons for legal reasons. */
function GithubIcon({ size = 16, class: cls }: { size?: number; class?: string }) {
  return (
    <svg class={cls} width={size} height={size} viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
    </svg>
  );
}
import { API } from './api';
import Sidebar from './components/Sidebar';
import type { SectionId } from './components/Sidebar';
import ServicesPanel from './components/ServicesPanel';
import SchemaForm from './components/SchemaForm';
import JenkinsfilePanel from './components/JenkinsfilePanel';
import ConfigTransfer from './components/ConfigTransfer';
import type {
  ConfigData,
  Schemas,
  Scope,
  ServiceStatuses,
} from './types';

/**
 * Section definitions — maps each UI section to its backend scope(s)
 * and display metadata. Order here determines render order.
 */
const SECTION_SCOPES: Record<string, { scopes: Scope[]; title: string; description: string }> = {
  telegram: {
    scopes: ['bot'],
    title: 'Telegram',
    description: 'Bot identity, chat permissions, and application settings.',
  },
  jenkins: {
    scopes: ['agent', 'builds'],
    title: 'Jenkins',
    description: 'Jenkins agent connection, build orchestration, and VPN configuration.',
  },
  storage: {
    scopes: ['file_manager'],
    title: 'Storage',
    description: 'File storage backend and Google Drive integration.',
  },
};

export default function App() {
  const [activeTab, setActiveTab] = useState<SectionId>('services');
  const [schemas, setSchemas] = useState<Schemas | null>(null);
  const [config, setConfig] = useState<ConfigData | null>(null);
  const [statuses, setStatuses] = useState<ServiceStatuses | null>(null);
  const [version, setVersion] = useState<string | null>(null);
  const [githubUrl, setGithubUrl] = useState<string | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [reloadSeq, setReloadSeq] = useState(0);
  const [dirtyScopes, setDirtyScopes] = useState<Record<Scope, boolean>>({
    bot: false,
    agent: false,
    file_manager: false,
    builds: false,
  });

  const handleDirtyChange = useCallback((scope: Scope, isDirty: boolean) => {
    setDirtyScopes((prev) => {
      if (prev[scope] === isDirty) return prev;
      return { ...prev, [scope]: isDirty };
    });
  }, []);

  // Initial data load
  useEffect(() => {
    async function load() {
      const [schemaResult, configResult] = await Promise.all([
        API.getSchema(),
        API.getConfig(),
      ]);

      if (!schemaResult && !configResult) {
        setLoadError(true);
        return;
      }

      setSchemas(schemaResult);
      setConfig(configResult);

      // Resolve GitHub URL from config or schema default
      if (schemaResult || configResult) {
        const configUrl =
          (configResult?.bot?.values as Record<string, Record<string, string>> | undefined)
            ?.project?.github_url ?? '';
        const schemaDefault =
          schemaResult?.bot?.fields?.find((f) => f.key === 'project.github_url')
            ?.default ?? '';
        const url = (configUrl || String(schemaDefault)).trim();
        if (url) setGithubUrl(url);
      }
    }

    async function loadVersion() {
      try {
        const res = await fetch('/api/version');
        if (!res.ok) return;
        const data = (await res.json()) as { version?: string };
        if (data.version) setVersion(data.version);
      } catch {
        // Silently ignore
      }
    }

    load();
    loadVersion();
  }, []);

  const handleStatusUpdate = useCallback((data: ServiceStatuses) => {
    setStatuses(data);
  }, []);

  const handleConfigReload = useCallback(async () => {
    const [schemaResult, configResult] = await Promise.all([
      API.getSchema(),
      API.getConfig(),
    ]);
    if (schemaResult) setSchemas(schemaResult);
    if (configResult) setConfig(configResult);
    setReloadSeq((prev) => prev + 1);
  }, []);

  // Fatal error state
  if (loadError) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '100vh',
          textAlign: 'center',
          padding: '2rem',
        }}
      >
        <h2 class="panel-title">Unable to Load Dashboard</h2>
        <p class="panel-desc" style={{ maxWidth: '400px' }}>
          Could not connect to the config-hub API. Check that all services are
          running.
        </p>
        <button class="btn btn-accent" onClick={() => location.reload()}>
          Retry
        </button>
      </div>
    );
  }


  return (
    <>
      {/* Header */}
      <header class="app-header">
        <div class="header-left">
          <img src="/static/favicon.svg" alt="App Icon" width={24} height={24} />
          <h1>Stack Control</h1>
          {version && (
            <span class="version-badge loaded">v{version}</span>
          )}
        </div>
        <div class="header-right">
          {githubUrl && (
            <a
              class="github-link"
              href={githubUrl}
              target="_blank"
              rel="noopener"
            >
              <GithubIcon class="github-icon" size={14} />
              GitHub
            </a>
          )}
        </div>
      </header>

      {/* Body */}
      <div class="app-body">
        <Sidebar
          activeTab={activeTab}
          onTabChange={setActiveTab}
          statuses={statuses}
          dirtyScopes={dirtyScopes}
        />

        <main class="content">
          {/* Services Panel */}
          {activeTab === 'services' && (
            <ServicesPanel
              statuses={statuses}
              onStatusUpdate={handleStatusUpdate}
              onNavigate={setActiveTab}
            />
          )}

          {/* Config sections: Telegram, Jenkins, Storage */}
          {schemas && Object.entries(SECTION_SCOPES).map(([sectionId, { scopes, title, description }]) => {
            const isVisible = activeTab === sectionId;

            // Check if all scopes in this section have empty schemas (ephemeral mode)
            const allEmpty = scopes.every(
              s => !schemas[s]?.fields?.length
            );

            if (allEmpty) {
              return (
                <div key={sectionId} style={{ display: isVisible ? 'block' : 'none' }}>
                  <h2 class="panel-title">{title}</h2>
                  <p class="panel-desc">{description}</p>
                  <p class="text-muted">
                    No configuration fields — current storage mode has no
                    configurable settings.
                  </p>
                </div>
              );
            }

            return (
              <div key={sectionId} style={{ display: isVisible ? 'block' : 'none' }}>
                <h2 class="panel-title">{title}</h2>
                <p class="panel-desc">{description}</p>

                {/* Render a SchemaForm for each scope in this section */}
                {scopes.map(scope => {
                  const schema = schemas[scope];
                  if (!schema?.fields?.length) return null;

                  const formKey = `${scope}-${reloadSeq}-${config?.[scope] ? JSON.stringify(config[scope]?.values) : 'empty'}`;
                  return (
                    <SchemaForm
                      key={formKey}
                      scope={scope}
                      schema={schema}
                      config={config?.[scope] ?? null}
                      onConfigReload={handleConfigReload}
                      onDirtyChange={handleDirtyChange}
                    />
                  );
                })}

              </div>
            );
          })}

          {/* Tools section — Jenkinsfile + Config Transfer */}
          {activeTab === 'tools' && (
            <div>
              <JenkinsfilePanel />
              <div style={{ marginTop: '24px' }}>
                <ConfigTransfer />
              </div>
            </div>
          )}
        </main>
      </div>
    </>
  );
}
