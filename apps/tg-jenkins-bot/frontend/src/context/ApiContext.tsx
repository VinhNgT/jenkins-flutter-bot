import { createContext } from 'preact';
import { useContext } from 'preact/hooks';
import type { ComponentChildren } from 'preact';
import type { WebAppAPI } from '../api';

const ApiContext = createContext<WebAppAPI | null>(null);

export function ApiProvider({
  api,
  children,
}: {
  api: WebAppAPI;
  children: ComponentChildren;
}) {
  return (
    <ApiContext.Provider value={api}>
      {children}
    </ApiContext.Provider>
  );
}

export function useAPI(): WebAppAPI {
  const context = useContext(ApiContext);
  if (!context) {
    throw new Error('useAPI must be used within an ApiProvider');
  }
  return context;
}
