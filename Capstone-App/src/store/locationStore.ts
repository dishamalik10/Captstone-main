import { create } from 'zustand';
import { Platform } from 'react-native';

const STORAGE_KEY = 'aura_styling_city';

interface LocationState {
  /** City typed on the Stylist screen; overrides the profile location for weather. */
  city: string | null;
  setCity: (city: string | null) => void;
}

function readStored(): string | null {
  if (Platform.OS !== 'web') return null;
  try {
    return globalThis.localStorage?.getItem(STORAGE_KEY) || null;
  } catch {
    return null;
  }
}

export const useLocationStore = create<LocationState>((set) => ({
  city: readStored(),
  setCity: (city) => {
    const value = city?.trim() || null;
    if (Platform.OS === 'web') {
      try {
        if (value) globalThis.localStorage?.setItem(STORAGE_KEY, value);
        else globalThis.localStorage?.removeItem(STORAGE_KEY);
      } catch {
        // storage unavailable: keep the city for this session only
      }
    }
    set({ city: value });
  },
}));
