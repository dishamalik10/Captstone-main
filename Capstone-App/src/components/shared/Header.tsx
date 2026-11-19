import { View, Text, Pressable } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { hapticLight } from '@/utils/haptics';
import { cn } from '@/utils/helpers';
import { useThemeColors } from '@/hooks/useThemeColors';

interface HeaderProps {
  title?: string;
  subtitle?: string;
  showBack?: boolean;
  onBack?: () => void;
  rightAction?: React.ReactNode;
  className?: string;
}

export function Header({ title, subtitle, showBack, onBack, rightAction, className }: HeaderProps) {
  const insets = useSafeAreaInsets();
  const palette = useThemeColors();

  return (
    <View
      className={cn('bg-background px-4 pb-3 border-b border-border', className)}
      // ScreenWrapper already applies the top inset; this only adds breathing room.
      style={{ paddingTop: insets.top > 0 ? 6 : 12 }}
    >
      <View className="flex-row items-center justify-between min-h-11">
        {showBack ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Go back"
            hitSlop={6}
            onPress={() => {
              hapticLight();
              onBack?.();
            }}
            className="w-11 h-11 rounded-full border border-border items-center justify-center hover:bg-surface-raised"
          >
            <Ionicons name="chevron-back" size={20} color={palette.textPrimary} />
          </Pressable>
        ) : (
          <View className="w-11" />
        )}
        {title ? (
          <View className="flex-1 items-center px-2">
            <Text accessibilityRole="header" numberOfLines={1} className="text-text-primary font-display text-xl">
              {title}
            </Text>
            {subtitle && (
              <Text numberOfLines={1} className="text-text-secondary font-body text-xs mt-0.5">
                {subtitle}
              </Text>
            )}
          </View>
        ) : (
          <View className="flex-1" />
        )}
        {rightAction ?? <View className="w-11" />}
      </View>
    </View>
  );
}
