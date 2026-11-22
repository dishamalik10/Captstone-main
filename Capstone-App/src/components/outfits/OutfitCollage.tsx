import { View } from 'react-native';
import type { ImageContentFit } from 'expo-image';
import { AppImage } from '@/components/shared/AppImage';
import type { Outfit } from '@/types';
import { cn } from '@/utils/helpers';

interface OutfitCollageProps {
  outfit: Pick<Outfit, 'imageUrl' | 'itemImages'>;
  className?: string;
  contentFit?: ImageContentFit;
}

/**
 * Shows every piece of an outfit together: two pieces side by side, three as one tall
 * piece beside two stacked, four as a 2×2 grid. Falls back to the single outfit image.
 */
export function OutfitCollage({ outfit, className, contentFit = 'cover' }: OutfitCollageProps) {
  const pieces = (outfit.itemImages ?? []).filter((piece) => piece.url).slice(0, 4);

  if (pieces.length < 2) {
    const uri = pieces[0]?.url ?? outfit.imageUrl;
    return (
      <AppImage
        source={{ uri }}
        className={cn('w-full h-full', className)}
        contentFit={contentFit}
        accessibilityLabel={pieces[0]?.label}
      />
    );
  }

  const tile = (piece: (typeof pieces)[number]) => (
    <AppImage
      key={piece.url}
      source={{ uri: piece.url }}
      className="flex-1 w-full"
      contentFit={contentFit}
      accessibilityLabel={piece.label}
    />
  );

  const columns =
    pieces.length === 2
      ? [[pieces[0]], [pieces[1]]]
      : pieces.length === 3
        ? [[pieces[0]], [pieces[1], pieces[2]]]
        : [[pieces[0], pieces[2]], [pieces[1], pieces[3]]];

  return (
    <View className={cn('w-full h-full flex-row gap-px bg-border', className)}>
      {columns.map((column, index) => (
        <View key={index} className="flex-1 gap-px">
          {column.map(tile)}
        </View>
      ))}
    </View>
  );
}
