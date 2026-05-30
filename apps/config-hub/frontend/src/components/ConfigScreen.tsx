/**
 * ConfigScreen — Detail screen for editing a configuration section.
 *
 * Renders SchemaForm components for each scope within the selected
 * section. Displayed via stack navigator push from HomeScreen.
 */

import { ChevronLeft } from 'lucide-preact';
import SchemaForm from './SchemaForm';
import type { ConfigData, Schemas, Scope } from '../types';

/** Section definitions — maps each UI section to backend scope(s). */
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

interface ConfigScreenProps {
  sectionId: string;
  schemas: Schemas | null;
  config: ConfigData | null;
  reloadSeq: number;
  onConfigReload: () => Promise<void>;
  onDirtyChange: (scope: Scope, isDirty: boolean) => void;
  onBack: () => void;
}

export default function ConfigScreen({
  sectionId,
  schemas,
  config,
  reloadSeq,
  onConfigReload,
  onDirtyChange,
  onBack,
}: ConfigScreenProps) {
  const section = SECTION_SCOPES[sectionId];
  if (!section) return null;

  const { scopes, title, description } = section;

  const allEmpty = schemas
    ? scopes.every(s => !schemas[s]?.fields?.length)
    : true;

  return (
    <div class="container">
      <header>
        <button class="back-button" onClick={onBack}>
          <ChevronLeft size={20} />
          Back
        </button>
      </header>

      <h2 class="panel-title">{title}</h2>
      <p class="panel-desc">{description}</p>

      {allEmpty ? (
        <p class="text-muted">
          No configuration fields — current storage mode has no
          configurable settings.
        </p>
      ) : (
        schemas && scopes.map(scope => {
          const schema = schemas[scope];
          if (!schema?.fields?.length) return null;

          const formKey = `${scope}-${reloadSeq}-${config?.[scope] ? JSON.stringify(config[scope]?.values) : 'empty'}`;
          return (
            <SchemaForm
              key={formKey}
              scope={scope}
              schema={schema}
              config={config?.[scope] ?? null}
              onConfigReload={onConfigReload}
              onDirtyChange={onDirtyChange}
            />
          );
        })
      )}
    </div>
  );
}
