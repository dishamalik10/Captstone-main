import { useEffect, useState } from 'react';
import { Modal as RNModal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { AppImage } from '@/components/shared/AppImage';
import { Button } from '@/components/ui/Button';
import { Chip } from '@/components/ui/Chip';
import { Input } from '@/components/ui/Input';
import { CLOTHING_CATEGORIES } from '@/constants/categories';
import { withAlpha } from '@/constants/theme';
import { useThemeColors } from '@/hooks/useThemeColors';
import type { ImportPreview } from '@/services';
import type { ClothingCategory } from '@/types';

const CATEGORY_OPTIONS = CLOTHING_CATEGORIES.filter(
  (option): option is { key: ClothingCategory; label: string } => option.key !== 'all',
);

interface ImportPreviewSheetProps {
  preview: ImportPreview | null;
  saving: boolean;
  onConfirm: (choice: 'cutout' | 'original', category: ClothingCategory, index: number, sizeLabel: string) => void;
  onCancel: () => void;
}

/**
 * Confirm a new wardrobe item (ENGINEERING_PLAN 4.2b): the garment cut out of a photo of
 * someone wearing it, in the category the user confirms. Three choices: "Looks right",
 * "Pick a different piece" (the next cut-out, or another category) and "Use the original photo".
 */
export function ImportPreviewSheet({ preview, saving, onConfirm, onCancel }: ImportPreviewSheetProps) {
  const palette = useThemeColors();
  const [category, setCategory] = useState<ClothingCategory>('tops');
  const [index, setIndex] = useState(0);
  const [size, setSize] = useState('');

  useEffect(() => {
    if (preview) {
      setCategory(preview.suggestedCategory ?? 'tops');
      setIndex(0);
      setSize(preview.suggestedSize ?? '');
    }
  }, [preview]);

  if (!preview) return null;
  const found = preview.candidates[category] ?? [];
  const candidate = found[index] ?? null;
  const imageUrl = candidate?.imageUrl ?? preview.originalUrl;

  const message = !preview.personFound
    ? 'Choose what this is, then add it.'
    : candidate
      ? `We kept only the ${CATEGORY_OPTIONS.find((o) => o.key === category)?.label.toLowerCase() ?? 'garment'} from the photo. Is this the piece you want?`
      : 'We couldn’t find this kind of piece in the photo. Choose another category, or use the original photo.';

  return (
    <RNModal visible transparent animationType="slide" onRequestClose={onCancel} statusBarTranslucent>
      <Pressable accessibilityLabel="Cancel" onPress={onCancel} style={[StyleSheet.absoluteFill, { backgroundColor: withAlpha(palette.scrim, 0.4) }]} />
      <View accessibilityViewIsModal className="mt-auto bg-surface rounded-t-lg border-t border-border w-full max-w-xl self-center" style={{ maxHeight: '92%' }}>
        <ScrollView contentContainerStyle={{ padding: 20, paddingBottom: 32 }}>
          <Text accessibilityRole="header" className="text-text-primary font-display text-2xl mb-1">
            {preview.sourceTitle ?? 'Add to your wardrobe'}
          </Text>
          <Text className="text-text-secondary font-body text-sm mb-4">{message}</Text>
          <AppImage
            source={{ uri: imageUrl }}
            className="w-full rounded-md bg-surface-raised"
            style={{ aspectRatio: 3 / 4 }}
            contentFit="contain"
            accessibilityLabel={candidate ? `Cut-out: ${candidate.label}` : 'Original photo'}
          />
          <Text className="text-text-primary font-body-medium text-sm mt-4 mb-2">What is it?</Text>
          <View className="flex-row flex-wrap">
            {CATEGORY_OPTIONS.map((option) => (
              <Chip
                key={option.key}
                label={option.label}
                selected={category === option.key}
                onPress={() => { setCategory(option.key); setIndex(0); }}
              />
            ))}
          </View>
          {category !== 'shoes' && category !== 'accessories' && (
            <Input
              label="Size (optional)"
              value={size}
              onChangeText={setSize}
              maxLength={20}
              autoCapitalize="characters"
              hint={preview.suggestedSize ? 'Read from the shop page. Change it if you bought another size.' : 'For example M, UK 12 or 32/32. Used for size advice.'}
              containerClassName="mt-3"
            />
          )}
          <View className="gap-3 mt-3">
            {candidate ? (
              <>
                <Button label="Looks right" loading={saving} disabled={saving} onPress={() => onConfirm('cutout', category, candidate.index, size)} />
                {found.length > 1 && (
                  <Button variant="secondary" label="Pick a different piece" disabled={saving} onPress={() => setIndex((index + 1) % found.length)} />
                )}
                <Button variant="secondary" label="Use the original photo" disabled={saving} onPress={() => onConfirm('original', category, 0, size)} />
              </>
            ) : (
              <Button
                label={preview.personFound ? 'Use the original photo' : 'Add to wardrobe'}
                loading={saving}
                disabled={saving}
                onPress={() => onConfirm('original', category, 0, size)}
              />
            )}
            <Button variant="ghost" label="Cancel" disabled={saving} onPress={onCancel} />
          </View>
          {preview.personFound && found.length <= 1 && (
            <Text className="text-text-tertiary font-body text-xs mt-3">
              Not the right piece? Pick another category above to see what else is in the photo.
            </Text>
          )}
        </ScrollView>
      </View>
    </RNModal>
  );
}
