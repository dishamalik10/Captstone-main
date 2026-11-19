import { View, Text, Pressable } from 'react-native';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { Ionicons } from '@expo/vector-icons';
import { ScreenWrapper } from './ScreenWrapper';
import { KeyboardAwareScroll } from './KeyboardAwareScroll';
import { Wordmark } from './Wordmark';
import { useThemeColors } from '@/hooks/useThemeColors';
import { layout, motion } from '@/constants/theme';
import { hapticLight } from '@/utils/haptics';

interface AuthScaffoldProps {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  onBack?: () => void;
  /** Render without the keyboard-aware scroll (for screens that manage their own). */
  scroll?: boolean;
}

/** Shared frame for the auth flow: wordmark bar, editorial title block, a capped form column. */
export function AuthScaffold({ title, subtitle, children, footer, onBack, scroll = true }: AuthScaffoldProps) {
  const palette = useThemeColors();

  const body = (
    <View style={{ width: '100%', maxWidth: layout.form, alignSelf: 'center' }} className="px-6">
      <Animated.View entering={FadeInDown.duration(motion.long)} className="mt-8 mb-8">
        <Text accessibilityRole="header" className="text-text-primary font-display text-4xl tracking-tight">
          {title}
        </Text>
        {subtitle ? (
          <Text className="text-text-secondary font-body text-base mt-3">{subtitle}</Text>
        ) : null}
      </Animated.View>
      {children}
      {footer ? <View className="mt-2">{footer}</View> : null}
    </View>
  );

  return (
    <ScreenWrapper className="flex-1">
      <View className="flex-row items-center justify-between px-4 h-14">
        {onBack ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Go back"
            onPress={() => {
              hapticLight();
              onBack();
            }}
            className="w-11 h-11 rounded-full items-center justify-center hover:bg-surface-raised"
          >
            <Ionicons name="chevron-back" size={22} color={palette.textPrimary} />
          </Pressable>
        ) : (
          <View className="w-11" />
        )}
        <Wordmark size={15} color={palette.textPrimary} />
        <View className="w-11" />
      </View>
      {scroll ? <KeyboardAwareScroll>{body}</KeyboardAwareScroll> : body}
    </ScreenWrapper>
  );
}

/** A hairline divider with a word in the middle. */
export function OrDivider({ label = 'or' }: { label?: string }) {
  return (
    <View className="flex-row items-center my-6 gap-3" accessibilityElementsHidden>
      <View className="flex-1 h-px bg-border" />
      <Text className="text-text-tertiary font-body text-sm">{label}</Text>
      <View className="flex-1 h-px bg-border" />
    </View>
  );
}
