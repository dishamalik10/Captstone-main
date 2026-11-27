import { useEffect, useState, useCallback } from 'react';
import { View, ActivityIndicator, Pressable, Text, useColorScheme } from 'react-native';
import * as ExpoSplashScreen from 'expo-splash-screen';
import { NavigationContainer, DarkTheme, DefaultTheme } from '@react-navigation/native';
import { AuthNavigator } from '@/navigation/AuthNavigator';
import { MainNavigator } from '@/navigation/MainNavigator';
import { useAuthStore } from '@/store/authStore';
import { SERVER_UNREACHABLE_MESSAGE } from '@/services/api';
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
  const { isAuthenticated, isLoading, serverUnreachable, hydrate, expireSession } = useAuthStore();
  const [retrying, setRetrying] = useState(false);
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

  if (serverUnreachable) {
    // The saved session is kept: the user is signed back in as soon as the server answers.
    const retry = () => {
      setRetrying(true);
      hydrate().finally(() => setRetrying(false));
    };
    return (
      <View
        onLayout={onLayoutReady}
        style={{ flex: 1, backgroundColor: palette.background, alignItems: 'center', justifyContent: 'center', padding: 24 }}
      >
        <Text accessibilityRole="header" style={{ color: palette.textPrimary, fontSize: 20, fontWeight: '600', marginBottom: 8, textAlign: 'center' }}>
          AURA is offline
        </Text>
        <Text style={{ color: palette.textSecondary, fontSize: 15, textAlign: 'center', marginBottom: 24, maxWidth: 360 }}>
          {SERVER_UNREACHABLE_MESSAGE}
        </Text>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Try again"
          onPress={retry}
          disabled={retrying}
          style={{ backgroundColor: palette.accent, borderRadius: 12, paddingVertical: 12, paddingHorizontal: 28, opacity: retrying ? 0.6 : 1 }}
        >
          {retrying ? <ActivityIndicator color={palette.background} /> : <Text style={{ color: palette.background, fontWeight: '600' }}>Try again</Text>}
        </Pressable>
        <Pressable accessibilityRole="button" onPress={() => void expireSession()} style={{ marginTop: 16, padding: 8 }}>
          <Text style={{ color: palette.textSecondary, textDecorationLine: 'underline' }}>Sign out instead</Text>
        </Pressable>
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
