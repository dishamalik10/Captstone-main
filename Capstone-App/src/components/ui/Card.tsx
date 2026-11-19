import { Pressable, type PressableProps } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withTiming } from 'react-native-reanimated';
import { cn } from '@/utils/helpers';
import { AnimatedPressable } from '@/utils/animatedInterop';
import { hapticLight } from '@/utils/haptics';
import { motion } from '@/constants/theme';


interface CardProps extends PressableProps {
  children: React.ReactNode;
  className?: string;
  pressable?: boolean;
}

const base = 'bg-surface rounded-md border border-border p-4';

export function Card({ children, className, pressable = false, onPress, ...props }: CardProps) {
  const scale = useSharedValue(1);
  const animStyle = useAnimatedStyle(() => ({ transform: [{ scale: scale.value }] }));

  if (!pressable) {
    return <Animated.View className={cn(base, className)}>{children}</Animated.View>;
  }

  return (
    <AnimatedPressable
      accessibilityRole="button"
      style={animStyle}
      onPressIn={() => {
        scale.value = withTiming(0.985, { duration: motion.micro });
      }}
      onPressOut={() => {
        scale.value = withTiming(1, { duration: motion.micro });
      }}
      onPress={(e) => {
        hapticLight();
        onPress?.(e);
      }}
      className={cn(base, 'hover:border-border-strong', className)}
      {...props}
    >
      {children}
    </AnimatedPressable>
  );
}
