import { View, Text } from 'react-native';
import Animated, { FadeIn } from 'react-native-reanimated';
import { Ionicons } from '@expo/vector-icons';
import { Button } from '@/components/ui/Button';
import { useThemeColors } from '@/hooks/useThemeColors';
import { motion } from '@/constants/theme';

interface EmptyStateProps {
  icon?: keyof typeof Ionicons.glyphMap;
  title: string;
  message: string;
  actionLabel?: string;
  onAction?: () => void;
}

export function EmptyState({
  icon = 'shirt-outline',
  title,
  message,
  actionLabel,
  onAction,
}: EmptyStateProps) {
  const palette = useThemeColors();
  return (
    <Animated.View entering={FadeIn.duration(motion.long)} className="flex-1 items-center justify-center px-8 py-12">
      <View className="w-28 h-28 rounded-full border border-border items-center justify-center mb-6">
        <View className="w-20 h-20 rounded-full bg-surface border border-border items-center justify-center">
          <Ionicons name={icon} size={30} color={palette.textPrimary} />
        </View>
      </View>
      <Text accessibilityRole="header" className="text-text-primary font-display text-2xl mb-2 text-center">
        {title}
      </Text>
      <Text className="text-text-secondary font-body text-base text-center mb-8 max-w-xs">{message}</Text>
      {actionLabel && onAction && <Button label={actionLabel} onPress={onAction} icon="add" />}
    </Animated.View>
  );
}
