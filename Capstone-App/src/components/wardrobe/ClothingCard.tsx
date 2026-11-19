import { View, Text, Pressable } from 'react-native';
import { AppImage } from '@/components/shared/AppImage';
import type { ClothingItem } from '@/types';
import { hapticLight, hapticMedium } from '@/utils/haptics';
import { cn } from '@/utils/helpers';

interface ClothingCardProps {
  item: ClothingItem;
  onPress?: () => void;
  onLongPress?: () => void;
  className?: string;
}

export function ClothingCard({ item, onPress, onLongPress, className }: ClothingCardProps) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${item.name}${item.brand ? ` by ${item.brand}` : ''}, ${item.category}`}
      accessibilityHint="Opens details. Long press for more actions."
      onPress={() => {
        hapticLight();
        onPress?.();
      }}
      onLongPress={() => {
        hapticMedium();
        onLongPress?.();
      }}
      className={cn('w-[48%] max-w-72 m-1 mb-4 group', className)}
    >
      <View className="aspect-[4/5] rounded-md overflow-hidden bg-surface border border-border group-hover:border-border-strong">
        <AppImage source={{ uri: item.imageUrl }} className="w-full h-full" contentFit="cover" />
        <View className="absolute top-2 left-2 rounded-sm px-2 py-0.5 bg-background/85">
          <Text className="text-text-primary font-body-medium text-[11px] capitalize">{item.category}</Text>
        </View>
      </View>
      <View className="flex-row items-center mt-2.5 gap-2">
        <View
          accessibilityLabel={`Colour ${item.color}`}
          className="w-3 h-3 rounded-full border border-border-strong"
          style={{ backgroundColor: item.colorHex }}
        />
        <Text className="text-text-primary font-body-medium text-sm flex-1" numberOfLines={1}>
          {item.name}
        </Text>
      </View>
      {!!item.brand && (
        <Text className="text-text-tertiary font-body text-xs mt-0.5 ml-5" numberOfLines={1}>
          {item.brand}
        </Text>
      )}
    </Pressable>
  );
}
