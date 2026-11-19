import { useEffect } from 'react';
import { View, Text } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useAuthStore } from '@/store/authStore';
import { ONBOARDING_KEY } from '@/constants/storage';
import { Wordmark } from '@/components/shared/Wordmark';
import { useThemeColors } from '@/hooks/useThemeColors';
import { fonts } from '@/constants/theme';

interface SplashScreenProps {
  onNavigate: (route: 'Onboarding' | 'Login' | 'Main') => void;
}

export function SplashScreen({ onNavigate }: SplashScreenProps) {
  const hydrate = useAuthStore((s) => s.hydrate);
  const palette = useThemeColors();

  useEffect(() => {
    let cancelled = false;

    const boot = async () => {
      try {
        await hydrate();
        const seen = await AsyncStorage.getItem(ONBOARDING_KEY);
        if (cancelled) return;

        setTimeout(() => {
          if (cancelled) return;
          if (useAuthStore.getState().isAuthenticated) {
            onNavigate('Main');
          } else if (!seen) {
            onNavigate('Onboarding');
          } else {
            onNavigate('Login');
          }
        }, 1500);
      } catch {
        if (!cancelled) onNavigate('Login');
      }
    };

    boot();
    return () => {
      cancelled = true;
    };
  }, [hydrate, onNavigate]);

  return (
    <View style={{ flex: 1, backgroundColor: palette.background, alignItems: 'center', justifyContent: 'center' }}>
      <Wordmark size={34} color={palette.textPrimary} />
      <Text style={{ color: palette.textSecondary, fontFamily: fonts.body, fontSize: 14, marginTop: 12 }}>
        Your personal stylist
      </Text>
    </View>
  );
}
