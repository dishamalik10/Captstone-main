import { View, Text, Pressable } from 'react-native';
import { AppImage } from '@/components/shared/AppImage';
import { OutfitCollage } from '@/components/outfits/OutfitCollage';
import { GradientScrim } from '@/components/shared/GradientScrim';
import type { Outfit } from '@/types';
import { useWardrobeStore } from '@/store/wardrobeStore';
import { hapticLight } from '@/utils/haptics';
import { cn } from '@/utils/helpers';
import { landing } from '@/constants/theme';

interface OutfitCardProps {
  outfit: Outfit;
  compact?: boolean;
  onPress?: () => void;
  className?: string;
}

export function OutfitCard({ outfit, compact, onPress, className }: OutfitCardProps) {
  const items = useWardrobeStore((s) => s.items);
  const outfitItems = items.filter((i) => outfit.itemIds.includes(i.id));

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={outfit.itemImages?.length ? `${outfit.name}: ${outfit.itemImages.map((p) => p.label).join(', ')}` : outfit.name}
      onPress={() => {
        hapticLight();
        onPress?.();
      }}
      className={cn(
        'bg-surface rounded-md border border-border overflow-hidden hover:border-border-strong',
        className,
      )}
    >
      <View className={cn('relative', compact ? 'h-64' : 'h-80')}>
        <OutfitCollage outfit={outfit} />
        <GradientScrim color={landing.night} opacity={0.82} from={0.55} />
        <View className="absolute bottom-3 left-4 right-4">
          <Text
            numberOfLines={compact ? 2 : 1}
            className={cn('font-display', compact ? 'text-lg' : 'text-2xl')}
            style={{ color: landing.inkPaper }}
          >
            {outfit.name}
          </Text>
          {!compact && (
            <Text numberOfLines={2} className="font-body text-sm mt-1" style={{ color: landing.nightMuted }}>
              {outfit.explanation}
            </Text>
          )}
        </View>
      </View>
      {!compact && outfitItems.length > 0 && (
        <View className="flex-row px-4 py-3 gap-2 items-center">
          {outfitItems.slice(0, 4).map((item) => (
            <AppImage
              key={item.id}
              source={{ uri: item.imageUrl }}
              className="w-11 h-11 rounded-sm border border-border"
              contentFit="cover"
              accessibilityLabel={item.name}
            />
          ))}
          <Text className="text-text-tertiary font-body text-xs ml-1">
            {outfitItems.length} {outfitItems.length === 1 ? 'piece' : 'pieces'} from your wardrobe
          </Text>
        </View>
      )}
    </Pressable>
  );
}
