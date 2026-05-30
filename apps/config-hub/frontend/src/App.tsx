/**
 * App — Root application component with stack navigation.
 *
 * Manages global state: schemas, configs, service statuses.
 * Uses the useNavigator hook for iOS/Telegram-style push/pop
 * navigation between HomeScreen and detail screens.
 *
 * Screen structure:
 *   HomeScreen (always mounted) — services, config sections, tools
 *   ConfigScreen (detail) — configuration editing for a section
 *   ToolScreen (detail) — jenkinsfile preview, config transfer
 */

import { useCallback, useEffect, useState } from 'preact/hooks';
import { useNavigator } from './hooks/useNavigator';
import type { Screen } from './hooks/useNavigator';
import { API } from './api';
import HomeScreen from './components/HomeScreen';
import ConfigScreen from './components/ConfigScreen';
import JenkinsfilePanel from './components/JenkinsfilePanel';
import ConfigTransfer from './components/ConfigTransfer';
import { useConfirm } from './context/ConfirmDialog';
import type {
  ConfigData,
  Schemas,
  Scope,
  ServiceStatuses,
} from './types';

const SECTION_SCOPES: Record<string, Scope[]> = {
  telegram: ['bot'],
  jenkins: ['agent', 'builds'],
  storage: ['file_manager'],
};

export default function App() {
  const navigator = useNavigator();
  const confirm = useConfirm();
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

  const handleBack = useCallback(async () => {
    const activeScreen = navigator.current;
    if (activeScreen?.screen === 'config' && activeScreen.id) {
      const scopes = SECTION_SCOPES[activeScreen.id] || [];
      const hasUnsavedChanges = scopes.some((s) => dirtyScopes[s]);
      if (hasUnsavedChanges) {
        const confirmed = await confirm({
          title: 'Discard unsaved changes?',
          message: 'You have unsaved changes in this section. If you go back, these changes will be lost.',
          confirmLabel: 'Discard',
          danger: true,
        });
        if (!confirmed) return;
      }
    }
    navigator.pop();
  }, [navigator, dirtyScopes, confirm]);

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
        const res = await fetch('/api/webapp-admin/version');
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

  const handleNavigate = useCallback((screen: Screen) => {
    navigator.push(screen);
  }, [navigator]);

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

  // The active detail screen — either the current screen or the one
  // being animated out (delayed unmount during pop).
  const detailScreen = navigator.current ?? navigator.exiting;

  // CSS class on the viewport controls the transform animation.
  const vpClass = `nav-viewport${navigator.phase !== 'idle' ? ` nav-${navigator.phase}` : ''}`;

  return (
    <div class={vpClass}>
      <div class="nav-screen nav-screen--main">
        <HomeScreen
          statuses={statuses}
          onStatusUpdate={handleStatusUpdate}
          onNavigate={handleNavigate}
          version={version}
          githubUrl={githubUrl}
          dirtyScopes={dirtyScopes}
        />
      </div>
      {detailScreen && (
        <div class="nav-screen nav-screen--detail">
          {detailScreen.screen === 'config' && detailScreen.id && (
            <ConfigScreen
              sectionId={detailScreen.id}
              schemas={schemas}
              config={config}
              reloadSeq={reloadSeq}
              onConfigReload={handleConfigReload}
              onDirtyChange={handleDirtyChange}
              isActive={detailScreen === navigator.current}
              onBack={handleBack}
            />
          )}
          {detailScreen.screen === 'jenkinsfile' && (
            <JenkinsfilePanel
              isActive={detailScreen === navigator.current}
              onBack={handleBack}
            />
          )}
          {detailScreen.screen === 'transfer' && (
            <ConfigTransfer
              isActive={detailScreen === navigator.current}
              onBack={handleBack}
            />
          )}
        </div>
      )}
    </div>
  );
}
