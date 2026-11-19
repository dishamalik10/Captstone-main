import { create } from 'zustand';
import { useEffect } from 'react';
import { Text, View } from 'react-native';
import Animated, { FadeInDown, FadeOutDown } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useThemeColors } from '@/hooks/useThemeColors';
import { motion } from '@/constants/theme';

type ToastVariant = 'success' | 'error' | 'info';

interface ToastState {
  message: string;
  variant: ToastVariant;
  visible: boolean;
  show: (message: string, variant?: ToastVariant) => void;
  hide: () => void;
}

export const useToastStore = create<ToastState>((set) => ({
  message: '',
  variant: 'info',
  visible: false,
  show: (message, variant = 'info') => set({ message, variant, visible: true }),
  hide: () => set({ visible: false }),
}));

const icons: Record<ToastVariant, keyof typeof Ionicons.glyphMap> = {
  success: 'checkmark-circle',
  error: 'alert-circle',
  info: 'information-circle',
};

export function Toast() {
  const { message, variant, visible, hide } = useToastStore();
  const insets = useSafeAreaInsets();
  const palette = useThemeColors();
  const iconColor =
    variant === 'success' ? palette.success : variant === 'error' ? palette.destructive : palette.accent;

  useEffect(() => {
    if (visible) {
      const timer = setTimeout(hide, 3200);
      return () => clearTimeout(timer);
    }
  }, [visible, hide, message]);

  if (!visible) return null;

  return (
    <View
      pointerEvents="box-none"
      className="absolute left-0 right-0 items-center px-4 z-50"
      style={{ bottom: insets.bottom + 92 }}
    >
      <Animated.View
        entering={FadeInDown.duration(motion.short)}
        exiting={FadeOutDown.duration(motion.micro)}
        accessibilityRole="alert"
        accessibilityLiveRegion="polite"
        className="flex-row items-center gap-3 rounded-md border border-border bg-surface-raised px-4 py-3 w-full max-w-md"
      >
        <Ionicons name={icons[variant]} size={20} color={iconColor} />
        <Text className="font-body text-sm text-text-primary flex-1">{message}</Text>
      </Animated.View>
    </View>
  );
}
