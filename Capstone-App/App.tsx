import './global.css';
import '@/utils/animatedInterop';
import { useEffect, useCallback } from 'react';
import { View, ActivityIndicator } from 'react-native';
import * as ExpoSplashScreen from 'expo-splash-screen';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  useFonts,
  PlayfairDisplay_400Regular,
  PlayfairDisplay_500Medium,
  PlayfairDisplay_700Bold,
} from '@expo-google-fonts/playfair-display';
import { Inter_400Regular, Inter_500Medium, Inter_600SemiBold } from '@expo-google-fonts/inter';
import { StatusBar } from 'expo-status-bar';
import { RootNavigator } from '@/navigation/RootNavigator';
import { ErrorBoundary } from '@/components/shared/ErrorBoundary';
import { Toast } from '@/components/ui/Toast';
import { useAppearanceStore } from '@/store/appearanceStore';
import { cssVariables, palettes, themeVars } from '@/constants/theme';
import { useResolvedTheme } from '@/hooks/useThemeColors';

ExpoSplashScreen.preventAutoHideAsync().catch(() => {});

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 2, staleTime: 1000 * 60 * 5 },
  },
});

export default function App() {
  const hydrateAppearance = useAppearanceStore((state) => state.hydrate);
  const resolvedTheme = useResolvedTheme();
  const palette = palettes[resolvedTheme];
  const [fontsLoaded] = useFonts({
    PlayfairDisplay_400Regular,
    PlayfairDisplay_500Medium,
    PlayfairDisplay_700Bold,
    Inter_400Regular,
    Inter_500Medium,
    Inter_600SemiBold,
  });

  const onReady = useCallback(async () => {
    if (fontsLoaded) {
      await ExpoSplashScreen.hideAsync();
    }
  }, [fontsLoaded]);

  useEffect(() => {
    onReady();
  }, [onReady]);

  useEffect(() => {
    hydrateAppearance();
  }, [hydrateAppearance]);

  useEffect(() => {
    if (typeof document !== 'undefined') {
      const root = document.documentElement;
      root.dataset.theme = resolvedTheme;
      root.style.colorScheme = resolvedTheme;
      Object.entries(cssVariables(resolvedTheme)).forEach(([name, value]) => {
        root.style.setProperty(name, value);
      });
    }
  }, [resolvedTheme]);

  if (!fontsLoaded) {
    return (
      <View style={{ flex: 1, backgroundColor: palette.background, alignItems: 'center', justifyContent: 'center' }}>
        <ActivityIndicator size="large" color={palette.accent} />
      </View>
    );
  }

  return (
    <GestureHandlerRootView style={{ flex: 1, backgroundColor: palette.background }}>
      <View style={[{ flex: 1 }, themeVars[resolvedTheme]]}>
        <SafeAreaProvider>
          <QueryClientProvider client={queryClient}>
            <ErrorBoundary>
              <RootNavigator />
              <Toast />
              <StatusBar style={resolvedTheme === 'dark' ? 'light' : 'dark'} />
            </ErrorBoundary>
          </QueryClientProvider>
        </SafeAreaProvider>
      </View>
    </GestureHandlerRootView>
  );
}
