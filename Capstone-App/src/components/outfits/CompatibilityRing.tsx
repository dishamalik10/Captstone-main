import { View, Text } from 'react-native';
import Svg, { Circle } from 'react-native-svg';
import { cn } from '@/utils/helpers';
import { landing, withAlpha } from '@/constants/theme';

interface CompatibilityRingProps {
  score: number;
  size?: number;
  className?: string;
}

/**
 * The ranking here comes from uncalibrated rule signals, so the indicator names
 * the method instead of printing a score that would read as a fashion grade.
 */
export function CompatibilityRing({ className, size = 72 }: CompatibilityRingProps) {
  const compact = size < 64;
  return (
    <View
      accessibilityLabel="Ranked by uncalibrated rule-based signals; not a fashion score"
      className={cn('flex-row items-center rounded-full px-3 py-1.5 gap-2', className)}
      style={{ backgroundColor: withAlpha(landing.night, 0.72) }}
    >
      <Svg width={12} height={12} viewBox="0 0 12 12" accessibilityElementsHidden>
        <Circle cx="6" cy="6" r="5" stroke={landing.goldOnInk} strokeWidth="1" fill="none" />
        <Circle cx="6" cy="6" r="2" fill={landing.goldOnInk} />
      </Svg>
      <Text className="font-body-medium text-xs" style={{ color: landing.inkPaper }}>
        {compact ? 'Rule signal' : 'Ranked by rule signals'}
      </Text>
    </View>
  );
}
