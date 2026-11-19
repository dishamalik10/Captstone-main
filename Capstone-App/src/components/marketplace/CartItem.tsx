import { View, Text, Pressable } from 'react-native';
import { AppImage } from '@/components/shared/AppImage';
import { Ionicons } from '@expo/vector-icons';
import type { Product } from '@/types';
import { formatCurrency } from '@/utils/helpers';
import { hapticLight } from '@/utils/haptics';
import { useThemeColors } from '@/hooks/useThemeColors';

interface CartItemRowProps {
  product: Product;
  quantity: number;
  onUpdateQty: (qty: number) => void;
  onRemove: () => void;
}

export function CartItemRow({ product, quantity, onUpdateQty, onRemove }: CartItemRowProps) {
  const palette = useThemeColors();
  return (
    <View className="flex-row items-center py-4 border-b border-border">
      <AppImage source={{ uri: product.imageUrls[0] }} className="w-16 h-20 rounded-sm" contentFit="cover" />
      <View className="flex-1 ml-4 mr-2">
        <Text className="text-text-primary font-body-medium text-base" numberOfLines={1}>
          {product.title}
        </Text>
        <Text className="text-text-secondary font-body text-sm tabular-nums mt-0.5">{formatCurrency(product.price)}</Text>
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
      <View className="flex-row items-center border border-border rounded-sm">
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Decrease quantity"
          onPress={() => {
            hapticLight();
            onUpdateQty(quantity - 1);
          }}
          className="w-10 h-10 items-center justify-center"
        >
          <Ionicons name="remove" size={16} color={palette.textPrimary} />
        </Pressable>
        <Text className="text-text-primary font-body-medium w-6 text-center tabular-nums">{quantity}</Text>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Increase quantity"
          onPress={() => {
            hapticLight();
            onUpdateQty(quantity + 1);
          }}
          className="w-10 h-10 items-center justify-center"
        >
          <Ionicons name="add" size={16} color={palette.textPrimary} />
        </Pressable>
      </View>
    </View>
  );
}
