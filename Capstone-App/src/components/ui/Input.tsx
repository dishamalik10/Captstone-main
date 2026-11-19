import { useEffect, useState } from 'react';
import { View, TextInput, Text, Pressable, type TextInputProps } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withTiming } from 'react-native-reanimated';
import { Ionicons } from '@expo/vector-icons';
import { cn } from '@/utils/helpers';
import { useThemeColors } from '@/hooks/useThemeColors';
import { motion } from '@/constants/theme';

interface InputProps extends TextInputProps {
  label: string;
  error?: string;
  isPassword?: boolean;
  containerClassName?: string;
  /** Optional helper line shown under the field when there is no error. */
  hint?: string;
}

export function Input({
  label,
  error,
  isPassword,
  containerClassName,
  value,
  onFocus,
  onBlur,
  hint,
  editable,
  ...props
}: InputProps) {
  const palette = useThemeColors();
  const [focused, setFocused] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const raised = focused || !!value;
  const progress = useSharedValue(raised ? 1 : 0);

  useEffect(() => {
    progress.value = withTiming(raised ? 1 : 0, { duration: motion.short });
  }, [raised, progress]);

  const labelStyle = useAnimatedStyle(() => ({
    transform: [
      { translateY: -11 * progress.value },
      { scale: 1 - 0.18 * progress.value },
    ],
  }));

  return (
    <View className={cn('mb-4', containerClassName)}>
      <View
        className={cn(
          'border rounded-sm px-4 pt-6 pb-2 min-h-14 bg-surface',
          error ? 'border-destructive' : focused ? 'border-accent' : 'border-border',
          editable === false && 'opacity-60',
        )}
      >
        <Animated.Text
          pointerEvents="none"
          style={[labelStyle, { transformOrigin: 'left center' }]}
          className={cn(
            'absolute left-4 top-[17px] font-body text-base',
            error ? 'text-destructive' : focused ? 'text-accent' : 'text-text-secondary',
          )}
        >
          {label}
        </Animated.Text>
        <TextInput
          accessibilityLabel={label}
          accessibilityHint={error}
          value={value}
          editable={editable}
          secureTextEntry={isPassword && !showPassword}
          onFocus={(e) => {
            setFocused(true);
            onFocus?.(e);
          }}
          onBlur={(e) => {
            setFocused(false);
            onBlur?.(e);
          }}
          selectionColor={palette.accent}
          cursorColor={palette.accent}
          className={cn('text-text-primary font-body text-base py-1', isPassword && 'pr-10')}
          placeholderTextColor={palette.textTertiary}
          {...props}
        />
        {isPassword && (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={showPassword ? 'Hide password' : 'Show password'}
            onPress={() => setShowPassword(!showPassword)}
            hitSlop={10}
            className="absolute right-2 top-2 w-10 h-10 items-center justify-center"
          >
            <Ionicons
              name={showPassword ? 'eye-off-outline' : 'eye-outline'}
              size={20}
              color={palette.textSecondary}
            />
          </Pressable>
        )}
      </View>
      {error ? (
        <View className="flex-row items-center mt-1.5 gap-1.5" accessibilityLiveRegion="polite">
          <Ionicons name="alert-circle-outline" size={14} color={palette.destructive} />
          <Text className="text-destructive text-sm font-body">{error}</Text>
        </View>
      ) : hint ? (
        <Text className="text-text-tertiary text-sm font-body mt-1.5">{hint}</Text>
      ) : null}
    </View>
  );
}
