import { View, Text, Pressable } from 'react-native';
import { AppImage } from '@/components/shared/AppImage';
import { Ionicons } from '@expo/vector-icons';
import type { Product } from '@/types';
import { formatCurrency } from '@/utils/helpers';
import { hapticLight } from '@/utils/haptics';
import { useThemeColors } from '@/hooks/useThemeColors';

interface CartItemRowProps {
  product: Product;
  onRemove: () => void;
}

/** One-off marketplace piece in the bag (no quantity: each listing is a single item). */
export function CartItemRow({ product, onRemove }: CartItemRowProps) {
  const palette = useThemeColors();
  return (
    <View className="flex-row items-center py-4 border-b border-border">
      <AppImage source={{ uri: product.imageUrls[0] }} className="w-16 h-20 rounded-sm" contentFit="cover" />
      <View className="flex-1 ml-4 mr-2">
        <Text className="text-text-primary font-body-medium text-base" numberOfLines={1}>
          {product.title}
        </Text>
        <Text className="text-text-secondary font-body text-sm tabular-nums mt-0.5">
          {formatCurrency(product.price)}{product.size ? ` · Size ${product.size}` : ''} · {product.seller.name}
        </Text>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`Remove ${product.title}`}
          hitSlop={8}
          onPress={() => {
            hapticLight();
            onRemove();
          }}
          className="flex-row items-center gap-1 mt-2 self-start"
        >
          <Ionicons name="trash-outline" size={14} color={palette.destructive} />
          <Text className="text-destructive font-body text-xs">Remove</Text>
        </Pressable>
      </View>
    </View>
  );
}
