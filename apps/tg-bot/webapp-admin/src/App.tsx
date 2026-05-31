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
import { useNavigator, Navigator as NavigationContainer } from 'tg-ui-preact';
import { useAPI } from './context/ApiContext';
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

export type ScreenType = 'config' | 'jenkinsfile' | 'transfer';

export interface Screen {
  screen: ScreenType;
  id?: string;
}

const SECTION_SCOPES: Record<string, Scope[]> = {
  telegram: ['bot'],
  jenkins: ['agent', 'builds'],
  storage: ['file_manager'],
};

export default function App() {
  const api = useAPI();
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
        api.getSchema(),
        api.getConfig(),
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
      api.getSchema(),
      api.getConfig(),
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
          Could not connect to the service-hub API. Check that all services are
          running.
        </p>
        <button class="btn btn-accent" onClick={() => location.reload()}>
          Retry
        </button>
      </div>
    );
  }

  return (
    <NavigationContainer
      phase={navigator.phase}
      mainScreen={
        <HomeScreen
          statuses={statuses}
          onStatusUpdate={handleStatusUpdate}
          onNavigate={handleNavigate}
          version={version}
          githubUrl={githubUrl}
          dirtyScopes={dirtyScopes}
        />
      }
      detailScreen={
        navigator.current ? (
          <>
            {navigator.current.screen === 'config' && navigator.current.id && (
              <ConfigScreen
                sectionId={navigator.current.id}
                schemas={schemas}
                config={config}
                reloadSeq={reloadSeq}
                onConfigReload={handleConfigReload}
                onDirtyChange={handleDirtyChange}
                onBack={handleBack}
              />
            )}
            {navigator.current.screen === 'jenkinsfile' && (
              <JenkinsfilePanel
                onBack={handleBack}
              />
            )}
            {navigator.current.screen === 'transfer' && (
              <ConfigTransfer
                onBack={handleBack}
              />
            )}
          </>
        ) : null
      }
      exitingScreen={
        navigator.exiting ? (
          <>
            {navigator.exiting.screen === 'config' && navigator.exiting.id && (
              <ConfigScreen
                sectionId={navigator.exiting.id}
                schemas={schemas}
                config={config}
                reloadSeq={reloadSeq}
                onConfigReload={handleConfigReload}
                onDirtyChange={handleDirtyChange}
                onBack={handleBack}
              />
            )}
            {navigator.exiting.screen === 'jenkinsfile' && (
              <JenkinsfilePanel
                onBack={handleBack}
              />
            )}
            {navigator.exiting.screen === 'transfer' && (
              <ConfigTransfer
                onBack={handleBack}
              />
            )}
          </>
        ) : null
      }
    />
  );
}
