import { createContext } from 'preact';

export interface BackButtonRegistry {
  hasPhysicalBackButton: boolean;
  register(onClick: () => void): () => void;
}

export const BackButtonContext = createContext<BackButtonRegistry | null>(null);
