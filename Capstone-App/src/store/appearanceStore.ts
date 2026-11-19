import { create } from 'zustand';
import { Platform } from 'react-native';
import { palettes } from '@/constants/theme';

export type AppearanceMode = 'dark' | 'light' | 'system';
export type ResolvedAppearance = 'dark' | 'light';

const STORAGE_KEY = 'aura_appearance';

interface AppearanceState {
  mode: AppearanceMode;
  hydrated: boolean;
  setMode: (mode: AppearanceMode) => void;
  hydrate: () => void;
}

/** Palettes now live in src/constants/theme.ts; this export is kept for existing imports. */
export const appearanceColors = palettes;

function saveMode(mode: AppearanceMode) {
  if (Platform.OS === 'web') {
    globalThis.localStorage?.setItem(STORAGE_KEY, mode);
  }
}

export const useAppearanceStore = create<AppearanceState>((set) => ({
  mode: 'light',
  hydrated: false,
  setMode: (mode) => {
    saveMode(mode);
    set({ mode });
  },
  hydrate: () => {
    const stored =
      Platform.OS === 'web'
        ? globalThis.localStorage?.getItem(STORAGE_KEY)
        : null;
    const mode =
      stored === 'dark' || stored === 'light' || stored === 'system'
        ? stored
        : 'light';
    set({ mode, hydrated: true });
  },
}));

