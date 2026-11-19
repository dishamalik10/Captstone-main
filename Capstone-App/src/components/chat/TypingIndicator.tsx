import { useEffect } from 'react';
import { View, Text } from 'react-native';
import Animated, {
  FadeIn,
  useAnimatedStyle,
  useSharedValue,
  withDelay,
  withRepeat,
  withSequence,
  withTiming,
  type SharedValue,
} from 'react-native-reanimated';

function useDot(delay: number): SharedValue<number> {
  const v = useSharedValue(0);
  useEffect(() => {
    v.value = withDelay(
      delay,
      withRepeat(withSequence(withTiming(1, { duration: 360 }), withTiming(0, { duration: 360 })), -1, false),
    );
  }, [v, delay]);
  return v;
}

export function TypingIndicator() {
  const d1 = useDot(0);
  const d2 = useDot(140);
  const d3 = useDot(280);
  const s1 = useAnimatedStyle(() => ({ opacity: 0.35 + 0.65 * d1.value, transform: [{ translateY: -2 * d1.value }] }));
  const s2 = useAnimatedStyle(() => ({ opacity: 0.35 + 0.65 * d2.value, transform: [{ translateY: -2 * d2.value }] }));
  const s3 = useAnimatedStyle(() => ({ opacity: 0.35 + 0.65 * d3.value, transform: [{ translateY: -2 * d3.value }] }));

  return (
    <Animated.View
      entering={FadeIn}
      accessibilityLabel="Stylist is typing"
      accessibilityLiveRegion="polite"
      className="flex-row items-center gap-2.5 px-4 mb-4"
    >
      <View className="w-8 h-8 rounded-full border border-accent/50 bg-accent-soft items-center justify-center">
        <Text className="font-display text-accent text-sm">A</Text>
      </View>
      <View className="flex-row items-center gap-1.5 px-4 py-3.5 bg-surface rounded-2xl rounded-bl-sm border border-border">
        <Animated.View style={s1} className="w-1.5 h-1.5 rounded-full bg-text-secondary" />
        <Animated.View style={s2} className="w-1.5 h-1.5 rounded-full bg-text-secondary" />
        <Animated.View style={s3} className="w-1.5 h-1.5 rounded-full bg-text-secondary" />
      </View>
    </Animated.View>
  );
}
