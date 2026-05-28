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
import { Github } from 'lucide-preact';
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
              <Github class="github-icon" size={14} />
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
                    No configuration fields — ephemeral storage mode has no
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
