import { View, Text, Pressable } from 'react-native';
import { AppImage } from '@/components/shared/AppImage';
import { Badge } from '@/components/ui/Badge';
import type { Product } from '@/types';
import { formatCurrency } from '@/utils/helpers';
import { hapticLight } from '@/utils/haptics';
import { cn } from '@/utils/helpers';

interface ProductCardProps {
  product: Product;
  compact?: boolean;
  onPress?: () => void;
  className?: string;
}

export function ProductCard({ product, compact, onPress, className }: ProductCardProps) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${product.title}, ${formatCurrency(product.price)}`}
      onPress={() => {
        hapticLight();
        onPress?.();
      }}
      className={cn('flex-1 m-1 mb-4 group', className)}
    >
      <View className="aspect-[4/5] rounded-md overflow-hidden bg-surface border border-border relative group-hover:border-border-strong">
        <AppImage source={{ uri: product.imageUrls[0] }} className="w-full h-full" contentFit="cover" />
        {product.status !== 'active' ? (
          <View className="absolute top-2 left-2">
            <Badge label={product.status === 'sold' ? 'Sold' : 'Paused'} />
          </View>
        ) : product.isNew && (
          <View className="absolute top-2 left-2">
            <Badge label="New" variant="accent" />
          </View>
        )}
      </View>
      <Text className="text-text-primary font-body-medium text-sm mt-2.5" numberOfLines={1}>
        {product.title}
      </Text>
      <View className="flex-row items-baseline justify-between mt-0.5">
        <Text className="text-text-primary font-body-semibold text-base tabular-nums">
          {formatCurrency(product.price)}
        </Text>
        <Text className="text-text-tertiary font-body text-xs capitalize">
          {product.condition.replace('_', ' ')}
        </Text>
      </View>
      {!compact && (
        <Text className="text-text-tertiary font-body text-xs mt-1" numberOfLines={1}>
          {[product.size && `Size ${product.size}`, product.brand, product.seller.name].filter(Boolean).join(' · ')}
        </Text>
      )}
    </Pressable>
  );
}
