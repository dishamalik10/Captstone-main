import { View, Text, Pressable } from 'react-native';
import { AppImage } from '@/components/shared/AppImage';
import { GradientScrim } from '@/components/shared/GradientScrim';
import { CompatibilityRing } from '@/components/outfits/CompatibilityRing';
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
      accessibilityLabel={`${outfit.name}, ranked by uncalibrated wardrobe rule signals`}
      onPress={() => {
        hapticLight();
        onPress?.();
      }}
      className={cn(
        'bg-surface rounded-md border border-border overflow-hidden hover:border-border-strong',
        className,
      )}
    >
      <View className={cn('relative', compact ? 'h-44' : 'h-72')}>
        <AppImage source={{ uri: outfit.imageUrl }} className="w-full h-full" contentFit="cover" />
        <GradientScrim color={landing.night} opacity={0.82} from={0.3} />
        <View className="absolute top-3 right-3">
          <CompatibilityRing score={outfit.compatibilityScore} size={compact ? 56 : 72} />
        </View>
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
