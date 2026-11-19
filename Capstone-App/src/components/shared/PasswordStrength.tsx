import { View, Text } from 'react-native';
import { useThemeColors } from '@/hooks/useThemeColors';

interface PasswordStrengthProps {
  score: number;
  label: string;
}

/** Four segments that fill with the password's strength; colour follows the theme, not a fixed hex. */
export function PasswordStrength({ score, label }: PasswordStrengthProps) {
  const palette = useThemeColors();
  const tone = score <= 1 ? palette.destructive : score >= 4 ? palette.success : palette.warning;
  return (
    <View className="mb-4" accessibilityLabel={`Password strength: ${label}`} accessibilityLiveRegion="polite">
      <View className="flex-row gap-1.5">
        {[0, 1, 2, 3].map((i) => (
          <View
            key={i}
            className="flex-1 h-1 rounded-full"
            style={{ backgroundColor: i < score ? tone : palette.border }}
          />
        ))}
      </View>
      <Text className="font-body text-xs mt-1.5" style={{ color: tone }}>
        {label}
      </Text>
    </View>
  );
}
