import { createContext } from 'preact';
import { useContext } from 'preact/hooks';
import type { ComponentChildren } from 'preact';
import type { ConfigHubAPI } from '../api';

const ApiContext = createContext<ConfigHubAPI | null>(null);

export function ApiProvider({
  api,
  children,
}: {
  api: ConfigHubAPI;
  children: ComponentChildren;
}) {
  return (
    <ApiContext.Provider value={api}>
      {children}
    </ApiContext.Provider>
  );
}

export function useAPI(): ConfigHubAPI {
  const context = useContext(ApiContext);
  if (!context) {
    throw new Error('useAPI must be used within an ApiProvider');
  }
  return context;
}
