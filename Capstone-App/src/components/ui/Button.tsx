import { Pressable, ActivityIndicator, Text, View, type PressableProps } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withTiming } from 'react-native-reanimated';
import { Ionicons } from '@expo/vector-icons';
import { cn } from '@/utils/helpers';
import { AnimatedPressable } from '@/utils/animatedInterop';
import { hapticLight } from '@/utils/haptics';
import { useThemeColors } from '@/hooks/useThemeColors';
import { motion } from '@/constants/theme';

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'destructive';
type ButtonSize = 'sm' | 'md' | 'lg';

interface ButtonProps extends PressableProps {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  label: string;
  className?: string;
  /** Optional leading icon. */
  icon?: keyof typeof Ionicons.glyphMap;
  /** Optional trailing icon. */
  trailingIcon?: keyof typeof Ionicons.glyphMap;
}


const variantClasses: Record<ButtonVariant, string> = {
  primary: 'bg-primary border border-primary hover:opacity-90',
  secondary: 'border border-text-primary bg-transparent hover:bg-surface-raised',
  ghost: 'bg-transparent border border-transparent hover:bg-surface-raised',
  destructive: 'bg-transparent border border-destructive hover:bg-destructive/10',
};

const textVariantClasses: Record<ButtonVariant, string> = {
  primary: 'text-primary-ink',
  secondary: 'text-text-primary',
  ghost: 'text-text-primary',
  destructive: 'text-destructive',
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: 'min-h-10 px-4 rounded-sm',
  md: 'min-h-12 px-5 rounded-sm',
  lg: 'min-h-14 px-6 rounded-sm',
};

const textSizeClasses: Record<ButtonSize, string> = {
  sm: 'text-sm',
  md: 'text-base',
  lg: 'text-base',
};

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  label,
  className,
  disabled,
  onPress,
  icon,
  trailingIcon,
  ...props
}: ButtonProps) {
  const palette = useThemeColors();
  const scale = useSharedValue(1);
  const pressStyle = useAnimatedStyle(() => ({ transform: [{ scale: scale.value }] }));
  const isDisabled = disabled || loading;
  const iconColor =
    variant === 'primary'
      ? palette.primaryInk
      : variant === 'destructive'
        ? palette.destructive
        : palette.textPrimary;

  return (
    <AnimatedPressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: !!isDisabled, busy: loading }}
      disabled={isDisabled}
      onPressIn={() => {
        scale.value = withTiming(0.98, { duration: motion.micro });
      }}
      onPressOut={() => {
        scale.value = withTiming(1, { duration: motion.micro });
      }}
      onPress={(e) => {
        hapticLight();
        onPress?.(e);
      }}
      style={pressStyle}
      className={cn(
        'items-center justify-center flex-row',
        variantClasses[variant],
        sizeClasses[size],
        isDisabled && 'opacity-50',
        className,
      )}
      {...props}
    >
      {loading ? (
        <View className="flex-row items-center gap-2">
          <ActivityIndicator color={iconColor} size="small" />
          <Text className={cn('font-body-semibold', textVariantClasses[variant], textSizeClasses[size])}>
            {label}
          </Text>
        </View>
      ) : (
        <View className="flex-row items-center gap-2">
          {icon ? <Ionicons name={icon} size={size === 'sm' ? 16 : 18} color={iconColor} /> : null}
          <Text
            numberOfLines={1}
            className={cn('font-body-semibold', textVariantClasses[variant], textSizeClasses[size])}
          >
            {label}
          </Text>
          {trailingIcon ? (
            <Ionicons name={trailingIcon} size={size === 'sm' ? 16 : 18} color={iconColor} />
          ) : null}
        </View>
      )}
    </AnimatedPressable>
  );
}
