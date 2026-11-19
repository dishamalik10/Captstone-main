import { create } from 'zustand';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';
import type { User } from '@/types';
import { authService } from '@/services';
import { setApiToken } from '@/services/api';

const TOKEN_KEY = 'auth_token';

async function saveToken(token: string): Promise<void> {
  if (Platform.OS === 'web') {
    globalThis.localStorage?.setItem(TOKEN_KEY, token);
    return;
  }
  await SecureStore.setItemAsync(TOKEN_KEY, token);
}

async function readToken(): Promise<string | null> {
  if (Platform.OS === 'web') {
    return globalThis.localStorage?.getItem(TOKEN_KEY) ?? null;
  }
  return SecureStore.getItemAsync(TOKEN_KEY);
}

async function removeToken(): Promise<void> {
  if (Platform.OS === 'web') {
    globalThis.localStorage?.removeItem(TOKEN_KEY);
    return;
  }
  await SecureStore.deleteItemAsync(TOKEN_KEY);
}

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  hasSeenOnboarding: boolean;
  login: (user: User, token: string) => Promise<void>;
  logout: () => Promise<void>;
  updateProfile: (data: Partial<User>) => void;
  setHasSeenOnboarding: (value: boolean) => void;
  hydrate: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  token: null,
  isAuthenticated: false,
  isLoading: true,
  hasSeenOnboarding: false,

  login: async (user, token) => {
    await saveToken(token);
    setApiToken(token);
    set({ user, token, isAuthenticated: true });
  },

  logout: async () => {
    try {
      await authService.logout();
    } catch {
      // Always clear a local session even if the server is unavailable.
    }
    await removeToken();
    setApiToken(null);
    set({ user: null, token: null, isAuthenticated: false });
  },

  updateProfile: (data) => {
    const current = get().user;
    if (current) set({ user: { ...current, ...data } });
  },

  setHasSeenOnboarding: (value) => set({ hasSeenOnboarding: value }),

  hydrate: async () => {
    try {
      const token = await readToken();
      if (token) {
        setApiToken(token);
        const user = await authService.me();
        set({ user, token, isAuthenticated: true, isLoading: false });
      } else {
        set({ isLoading: false });
      }
    } catch {
      await removeToken();
      setApiToken(null);
      set({ user: null, token: null, isAuthenticated: false, isLoading: false });
    }
  },
}));
