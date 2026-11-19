import { View, Text } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Avatar } from '@/components/ui/Avatar';
import type { Seller } from '@/types';
import { useThemeColors } from '@/hooks/useThemeColors';

interface SellerBadgeProps {
  seller: Seller;
}

export function SellerBadge({ seller }: SellerBadgeProps) {
  const palette = useThemeColors();
  return (
    <View className="flex-row items-center gap-3">
      <Avatar uri={seller.avatarUrl} name={seller.name} size="md" />
      <View className="flex-1">
        <Text className="text-text-primary font-body-semibold text-base">{seller.name}</Text>
        <View className="flex-row items-center gap-1 mt-0.5">
          <Ionicons name="star" size={12} color={palette.accent} />
          <Text className="text-text-secondary font-body text-xs tabular-nums">{seller.rating}</Text>
          <Text className="text-text-tertiary font-body text-xs ml-2">Responds {seller.responseTime}</Text>
        </View>
      </View>
    </View>
  );
}
