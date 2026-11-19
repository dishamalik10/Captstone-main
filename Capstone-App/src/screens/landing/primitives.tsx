import { useEffect } from 'react';
import {
  Pressable,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
  type StyleProp,
  type TextStyle,
  type ViewStyle,
} from 'react-native';
import Animated, {
  useAnimatedReaction,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withDelay,
  withTiming,
  Easing,
  type SharedValue,
} from 'react-native-reanimated';
import { Ionicons } from '@expo/vector-icons';
import { AppImage } from '@/components/shared/AppImage';
import { fonts, landing, layout } from '@/constants/theme';
import { hapticLight } from '@/utils/haptics';
import type { SampleGarment } from './content';

export function useBreakpoints() {
  const { width, height } = useWindowDimensions();
  const wide = width >= 1024;
  const mid = width >= 720;
  return { width, height, wide, mid, gutter: mid ? 40 : 20 };
}

export function Container({ children, style }: { children: React.ReactNode; style?: StyleProp<ViewStyle> }) {
  const { gutter } = useBreakpoints();
  return (
    <View style={[{ width: '100%', maxWidth: layout.content + gutter * 2, alignSelf: 'center', paddingHorizontal: gutter }, style]}>
      {children}
    </View>
  );
}

/** Responsive type roles for the landing page. */
export function useType() {
  const { wide, mid } = useBreakpoints();
  return StyleSheet.create({
    display: {
      fontFamily: fonts.display,
      color: landing.ink,
      fontSize: wide ? 76 : mid ? 60 : 44,
      lineHeight: wide ? 80 : mid ? 64 : 48,
      letterSpacing: wide ? -1.8 : -1,
    },
    h2: {
      fontFamily: fonts.display,
      color: landing.ink,
      fontSize: wide ? 52 : mid ? 42 : 34,
      lineHeight: wide ? 58 : mid ? 48 : 40,
      letterSpacing: wide ? -1 : -0.5,
    },
    h3: { fontFamily: fonts.display, color: landing.ink, fontSize: 24, lineHeight: 30, letterSpacing: -0.2 },
    lead: { fontFamily: fonts.body, color: landing.ink2, fontSize: mid ? 19 : 17, lineHeight: mid ? 30 : 27 },
    body: { fontFamily: fonts.body, color: landing.ink2, fontSize: 16, lineHeight: 25 },
    small: { fontFamily: fonts.body, color: landing.muted, fontSize: 14, lineHeight: 20 },
    label: { fontFamily: fonts.bodyMedium, color: landing.ink, fontSize: 14, lineHeight: 20 },
    numeral: { fontFamily: fonts.display, color: landing.gold, fontSize: 20, lineHeight: 24 },
  });
}

type LButtonVariant = 'ink' | 'outline' | 'text' | 'gold' | 'paper' | 'textLight';

export function LButton({
  label,
  onPress,
  variant = 'ink',
  icon,
  style,
  small,
}: {
  label: string;
  onPress: () => void;
  variant?: LButtonVariant;
  icon?: keyof typeof Ionicons.glyphMap;
  style?: StyleProp<ViewStyle>;
  small?: boolean;
}) {
  const fg =
    variant === 'ink' ? landing.inkPaper : variant === 'textLight' ? landing.terracottaInk : landing.ink;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={() => {
        hapticLight();
        onPress();
      }}
      style={(state) => {
        const hovered = (state as { hovered?: boolean }).hovered;
        const pressed = state.pressed;
        const base: ViewStyle = {
          minHeight: small ? 44 : 52,
          paddingHorizontal: variant === 'text' || variant === 'textLight' ? 4 : small ? 18 : 26,
          borderRadius: 4,
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 8,
          transform: [{ scale: pressed ? 0.98 : 1 }],
        };
        if (variant === 'ink') {
          return [base, { backgroundColor: hovered ? landing.ink2 : landing.ink }, style];
        }
        if (variant === 'paper') {
          return [base, { backgroundColor: hovered ? landing.paper2 : landing.paper }, style];
        }
        if (variant === 'gold') {
          return [base, { backgroundColor: hovered ? landing.inkPaper : landing.goldOnInk }, style];
        }
        if (variant === 'outline') {
          return [
            base,
            { borderWidth: 1, borderColor: landing.ink, backgroundColor: hovered ? landing.paper2 : 'transparent' },
            style,
          ];
        }
        return [base, { opacity: hovered ? 0.7 : 1 }, style];
      }}
    >
      <Text
        style={{
          fontFamily: fonts.bodySemibold,
          fontSize: small ? 14 : 16,
          color: fg,
          textDecorationLine: variant === 'text' || variant === 'textLight' ? 'underline' : 'none',
        }}
      >
        {label}
      </Text>
      {icon ? <Ionicons name={icon} size={small ? 15 : 17} color={fg} /> : null}
    </Pressable>
  );
}

/** One garment photograph with an optional wall label beneath it. */
export function Tile({
  garment,
  width,
  dim,
  showLabel,
  highlight,
  style,
}: {
  garment: SampleGarment;
  width: number;
  dim?: boolean;
  showLabel?: boolean;
  highlight?: boolean;
  style?: StyleProp<ViewStyle>;
}) {
  return (
    <View style={[{ width }, style]}>
      <View
        style={{
          width,
          aspectRatio: 4 / 5,
          borderRadius: 4,
          overflow: 'hidden',
          borderWidth: highlight ? 2 : 1,
          borderColor: highlight ? landing.ink : landing.rule,
          backgroundColor: landing.paper2,
          opacity: dim ? 0.38 : 1,
        }}
      >
        <AppImage
          source={{ uri: garment.image }}
          style={{ width: '100%', height: '100%', backgroundColor: landing.paper2 }}
          contentFit="cover"
          accessibilityLabel={garment.name}
        />
      </View>
      {showLabel ? (
        <Text numberOfLines={1} style={{ fontFamily: fonts.body, fontSize: 13, lineHeight: 18, color: dim ? landing.muted : landing.ink2, marginTop: 6 }}>
          {garment.name}
        </Text>
      ) : null}
    </View>
  );
}

/** A plain sentence-case caption in a hairline frame, used to mark demo content. */
export function DemoTag({ label, onDark }: { label: string; onDark?: boolean }) {
  return (
    <View
      style={{
        alignSelf: 'flex-start',
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
        paddingHorizontal: 10,
        paddingVertical: 4,
        borderRadius: 999,
        borderWidth: 1,
        borderColor: onDark ? landing.nightRule : landing.rule,
        backgroundColor: onDark ? landing.night2 : landing.card,
      }}
    >
      <Ionicons name="eye-outline" size={13} color={onDark ? landing.nightMuted : landing.muted} />
      <Text style={{ fontFamily: fonts.body, fontSize: 13, lineHeight: 18, color: onDark ? landing.nightMuted : landing.muted }}>
        {label}
      </Text>
    </View>
  );
}

/**
 * The page's one reveal: a fade with an 8px rise, staggered by index, run once
 * when `revealed` flips to 1. Under reduced motion the content is simply there.
 */
export function Reveal({
  revealed,
  index = 0,
  children,
  style,
}: {
  revealed: SharedValue<number>;
  index?: number;
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
}) {
  const reduceMotion = useReducedMotion();
  const progress = useSharedValue(reduceMotion ? 1 : 0);

  useEffect(() => {
    if (reduceMotion) progress.value = 1;
  }, [reduceMotion, progress]);

  useAnimatedReaction(
    () => revealed.value,
    (now, before) => {
      if (now === 1 && before !== 1 && progress.value < 1) {
        progress.value = withDelay(
          index * 90,
          withTiming(1, { duration: 520, easing: Easing.out(Easing.cubic) }),
        );
      }
    },
  );

  const animated = useAnimatedStyle(() => ({
    opacity: progress.value,
    transform: [{ translateY: (1 - progress.value) * 8 }],
  }));

  return <Animated.View style={[style, animated]}>{children}</Animated.View>;
}

export function Hairline({ color = landing.rule, style }: { color?: string; style?: StyleProp<ViewStyle> }) {
  return <View style={[{ height: StyleSheet.hairlineWidth * 2, backgroundColor: color }, style]} />;
}

export function SectionHead({
  title,
  lead,
  onDark,
  titleStyle,
}: {
  title: string;
  lead?: string;
  onDark?: boolean;
  titleStyle?: StyleProp<TextStyle>;
}) {
  const t = useType();
  return (
    <View style={{ maxWidth: 680 }}>
      <Text accessibilityRole="header" style={[t.h2, onDark && { color: landing.inkPaper }, titleStyle]}>
        {title}
      </Text>
      {lead ? (
        <Text style={[t.lead, { marginTop: 16 }, onDark && { color: landing.nightMuted }]}>{lead}</Text>
      ) : null}
    </View>
  );
}
