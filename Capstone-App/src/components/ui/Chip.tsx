import { Pressable, Text } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { cn } from '@/utils/helpers';
import { hapticLight } from '@/utils/haptics';
import { useThemeColors } from '@/hooks/useThemeColors';

interface ChipProps {
  label: string;
  selected?: boolean;
  onPress?: () => void;
  className?: string;
  /** Optional leading icon. */
  icon?: keyof typeof Ionicons.glyphMap;
}

export function Chip({ label, selected, onPress, className, icon }: ChipProps) {
  const palette = useThemeColors();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ selected }}
      hitSlop={4}
      onPress={() => {
        hapticLight();
        onPress?.();
      }}
      className={cn(
        'min-h-10 flex-row items-center px-4 rounded-full border mr-2 mb-2',
        selected
          ? 'bg-primary border-primary'
          : 'bg-transparent border-border hover:border-border-strong',
        className,
      )}
    >
      {icon ? (
        <Ionicons
          name={icon}
          size={15}
          color={selected ? palette.primaryInk : palette.textSecondary}
          style={{ marginRight: 6 }}
        />
      ) : null}
      <Text
        className={cn(
          'text-sm',
          selected ? 'text-primary-ink font-body-medium' : 'text-text-secondary font-body',
        )}
      >
        {label}
      </Text>
    </Pressable>
  );
}
