import { View, Text } from 'react-native';
import { cn } from '@/utils/helpers';

interface BadgeProps {
  label: string;
  variant?: 'default' | 'accent' | 'success' | 'destructive';
  className?: string;
}

const variants = {
  default: 'bg-surface-raised border-border',
  accent: 'bg-accent-soft border-accent/40',
  success: 'bg-success/10 border-success/40',
  destructive: 'bg-destructive/10 border-destructive/40',
};

const textVariants = {
  default: 'text-text-secondary',
  accent: 'text-accent',
  success: 'text-success',
  destructive: 'text-destructive',
};

export function Badge({ label, variant = 'default', className }: BadgeProps) {
  return (
    <View className={cn('self-start px-2 py-0.5 rounded-sm border', variants[variant], className)}>
      <Text className={cn('text-xs font-body-medium capitalize', textVariants[variant])}>{label}</Text>
    </View>
  );
}
