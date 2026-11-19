import { useEffect, useState, useCallback } from 'react';
import { View, ActivityIndicator, useColorScheme } from 'react-native';
import * as ExpoSplashScreen from 'expo-splash-screen';
import { NavigationContainer, DarkTheme, DefaultTheme } from '@react-navigation/native';
import { AuthNavigator } from '@/navigation/AuthNavigator';
import { MainNavigator } from '@/navigation/MainNavigator';
import { useAuthStore } from '@/store/authStore';
import { appearanceColors, useAppearanceStore } from '@/store/appearanceStore';

ExpoSplashScreen.preventAutoHideAsync().catch(() => {});

export function RootNavigator() {
  const systemScheme = useColorScheme();
  const appearanceMode = useAppearanceStore((state) => state.mode);
  const resolvedAppearance =
    appearanceMode === 'system'
      ? systemScheme === 'light' ? 'light' : 'dark'
      : appearanceMode;
  const palette = appearanceColors[resolvedAppearance];
  const baseTheme = resolvedAppearance === 'dark' ? DarkTheme : DefaultTheme;
  const navTheme = {
    ...baseTheme,
    colors: {
      ...baseTheme.colors,
      background: palette.background,
      card: palette.surface,
      text: palette.textPrimary,
      border: palette.border,
      primary: palette.accent,
    },
  };
  const { isAuthenticated, isLoading, hydrate } = useAuthStore();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    hydrate().finally(() => setReady(true));
  }, [hydrate]);

  const onLayoutReady = useCallback(async () => {
    if (ready && !isLoading) {
      await ExpoSplashScreen.hideAsync();
    }
  }, [ready, isLoading]);

  useEffect(() => {
    onLayoutReady();
  }, [onLayoutReady]);

  if (!ready || isLoading) {
    return (
      <View style={{ flex: 1, backgroundColor: palette.background, alignItems: 'center', justifyContent: 'center' }}>
        <ActivityIndicator size="large" color={palette.accent} />
      </View>
    );
  }

  return (
    <View style={{ flex: 1 }} onLayout={onLayoutReady}>
      <NavigationContainer theme={navTheme}>
        {isAuthenticated ? <MainNavigator /> : <AuthNavigator />}
      </NavigationContainer>
    </View>
  );
}
