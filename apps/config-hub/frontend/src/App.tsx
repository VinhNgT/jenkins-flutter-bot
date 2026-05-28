/**
 * App — Root application component.
 *
 * Manages global state: schemas, configs, service statuses, active tab.
 * Orchestrates data fetching on mount and delegates to child components.
 */

import { useCallback, useEffect, useState } from 'preact/hooks';
import { Github } from 'lucide-preact';
import { API } from './api';
import Sidebar from './components/Sidebar';
import type { TabId } from './components/Sidebar';
import Dashboard from './components/Dashboard';
import SchemaForm from './components/SchemaForm';
import JenkinsfilePanel from './components/JenkinsfilePanel';
import ConfigTransfer from './components/ConfigTransfer';
import VpnWidget from './components/VpnWidget';
import type {
  ConfigData,
  Schemas,
  Scope,
  ServiceStatuses,
} from './types';

const SCOPE_TABS: Scope[] = ['bot', 'builds', 'agent', 'file_manager'];

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>('dashboard');
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
          {/* Dashboard */}
          {activeTab === 'dashboard' && (
            <Dashboard
              statuses={statuses}
              onStatusUpdate={handleStatusUpdate}
              onNavigate={setActiveTab}
            />
          )}

          {/* Config tabs */}
          {schemas && SCOPE_TABS.map((scope) => {
            const schema = schemas[scope];
            if (!schema) return null;

            const isVisible = activeTab === scope;

            // Ephemeral mode: file_manager schema has no fields
            if (scope === 'file_manager' && !schema.fields?.length) {
              return (
                <div key={scope} style={{ display: isVisible ? 'block' : 'none' }}>
                  <h2 class="panel-title">{schema.title}</h2>
                  <p class="panel-desc" dangerouslySetInnerHTML={{ __html: schema.description }} />
                  <p class="text-muted">
                    No configuration fields — ephemeral storage mode has no
                    configurable settings.
                  </p>
                </div>
              );
            }

            const formKey = `${scope}-${reloadSeq}-${config?.[scope] ? JSON.stringify(config[scope]?.values) : 'empty'}`;
            return (
              <div key={scope} style={{ display: isVisible ? 'block' : 'none' }}>
                <SchemaForm
                  key={formKey}
                  scope={scope}
                  schema={schema}
                  config={config?.[scope] ?? null}
                  onConfigReload={handleConfigReload}
                  onDirtyChange={handleDirtyChange}
                />
                {/* VPN widget under the agent config form */}
                {scope === 'agent' && <VpnWidget />}
              </div>
            );
          })}

          {/* Jenkinsfile generator */}
          {activeTab === 'jenkinsfile' && <JenkinsfilePanel />}

          {/* Config transfer */}
          {activeTab === 'export' && <ConfigTransfer />}
        </main>
      </div>
    </>
  );
}
