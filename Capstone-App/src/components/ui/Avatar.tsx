import { View, Text } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { AppImage } from '@/components/shared/AppImage';
import { cn } from '@/utils/helpers';
import { resolveApiUrl } from '@/services/api';
import { useThemeColors } from '@/hooks/useThemeColors';

interface AvatarProps {
  uri?: string;
  size?: 'sm' | 'md' | 'lg' | 'xl';
  className?: string;
  /** Optional name, used for initials when there is no photo. */
  name?: string;
}

const sizes = { sm: 'w-8 h-8', md: 'w-12 h-12', lg: 'w-16 h-16', xl: 'w-24 h-24' };
const iconSizes = { sm: 16, md: 22, lg: 28, xl: 40 };
const textSizes = { sm: 'text-xs', md: 'text-base', lg: 'text-lg', xl: 'text-2xl' };

function initials(name?: string) {
  if (!name) return '';
  return name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('');
}

export function Avatar({ uri, size = 'md', className, name }: AvatarProps) {
  const palette = useThemeColors();
  const letters = initials(name);
  return (
    <View
      className={cn(
        'rounded-full overflow-hidden border border-border bg-surface-raised items-center justify-center',
        sizes[size],
        className,
      )}
    >
      {uri ? (
        <AppImage source={{ uri: uri.startsWith('/') ? resolveApiUrl(uri) : uri }} className="w-full h-full" contentFit="cover" accessibilityIgnoresInvertColors />
      ) : letters ? (
        <Text className={cn('font-display text-text-primary', textSizes[size])}>{letters}</Text>
      ) : (
        <Ionicons name="person-outline" size={iconSizes[size]} color={palette.textTertiary} />
      )}
    </View>
  );
}
