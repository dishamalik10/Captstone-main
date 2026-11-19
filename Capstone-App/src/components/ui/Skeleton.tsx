import { useEffect } from 'react';
import { View, type ViewProps } from 'react-native';
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
  interpolate,
  Easing,
  ReduceMotion,
} from 'react-native-reanimated';
import { cn } from '@/utils/helpers';

interface SkeletonProps extends ViewProps {
  className?: string;
}

export function Skeleton({ className, ...props }: SkeletonProps) {
  const shimmer = useSharedValue(0);

  useEffect(() => {
    shimmer.value = withRepeat(
      withTiming(1, { duration: 1100, easing: Easing.inOut(Easing.quad), reduceMotion: ReduceMotion.System }),
      -1,
      true,
    );
  }, [shimmer]);

  const style = useAnimatedStyle(() => ({
    opacity: interpolate(shimmer.value, [0, 1], [0.45, 0.9]),
  }));

  return (
    <Animated.View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={style}
      className={cn('bg-surface-raised rounded-sm', className)}
      {...props}
    />
  );
}

/** Matches OutfitCard: image block, title, one line of copy. */
export function SkeletonCard() {
  return (
    <View className="bg-surface rounded-md border border-border overflow-hidden mb-3">
      <Skeleton className="h-64 w-full rounded-none" />
      <View className="p-4">
        <Skeleton className="h-5 w-3/5 mb-2" />
        <Skeleton className="h-3.5 w-4/5" />
      </View>
    </View>
  );
}

/** Matches ClothingCard: square image, a name line, a brand line. */
export function SkeletonClothingCard() {
  return (
    <View className="w-[48%] m-1">
      <Skeleton className="w-full aspect-[4/5] rounded-md" />
      <Skeleton className="h-3.5 w-3/4 mt-3" />
      <Skeleton className="h-3 w-1/3 mt-2" />
    </View>
  );
}

/** A two-column grid of clothing card placeholders. */
export function SkeletonGrid({ count = 6 }: { count?: number }) {
  return (
    <View className="flex-row flex-wrap px-2" accessibilityLabel="Loading" accessibilityRole="progressbar">
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonClothingCard key={i} />
      ))}
    </View>
  );
}
