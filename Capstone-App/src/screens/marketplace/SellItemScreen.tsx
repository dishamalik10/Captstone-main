import { useState } from 'react';
import { View, Text, ScrollView, Pressable, Alert } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import * as ImagePicker from 'expo-image-picker';
import { Ionicons } from '@expo/vector-icons';
import { KeyboardAwareScroll } from '@/components/shared/KeyboardAwareScroll';
import { ScreenWrapper } from '@/components/shared/ScreenWrapper';
import { Header } from '@/components/shared/Header';
import { AppImage } from '@/components/shared/AppImage';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { Chip } from '@/components/ui/Chip';
import { useToastStore } from '@/components/ui/Toast';
import { useRefreshMarketplace, useWardrobeItems } from '@/hooks';
import { useThemeColors } from '@/hooks/useThemeColors';
import { marketplaceService, type UploadAsset } from '@/services';
import type { ClothingCategory, ClothingItem, ProductCondition } from '@/types';
import { cn } from '@/utils/helpers';
import { layout } from '@/constants/theme';

const MAX_PHOTOS = 5;
const CATEGORIES: { key: ClothingCategory; label: string }[] = [
  { key: 'tops', label: 'Tops' }, { key: 'bottoms', label: 'Bottoms' }, { key: 'dresses', label: 'Dresses' },
  { key: 'outerwear', label: 'Outerwear' }, { key: 'shoes', label: 'Shoes' }, { key: 'accessories', label: 'Accessories' },
];
const CONDITIONS: { key: ProductCondition; label: string }[] = [
  { key: 'new', label: 'New with tags' }, { key: 'like_new', label: 'Like new' },
  { key: 'good', label: 'Good' }, { key: 'fair', label: 'Fair' },
];

export function SellItemScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<Record<string, object | undefined>>>();
  const palette = useThemeColors();
  const showToast = useToastStore((s) => s.show);
  const refreshMarketplace = useRefreshMarketplace();
  const { data: wardrobe } = useWardrobeItems();
  const [photos, setPhotos] = useState<UploadAsset[]>([]);
  const [fromWardrobe, setFromWardrobe] = useState<ClothingItem | null>(null);
  const [form, setForm] = useState({ title: '', price: '', size: '', brand: '', description: '' });
  const [category, setCategory] = useState<ClothingCategory | null>(null);
  const [condition, setCondition] = useState<ProductCondition | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [publishing, setPublishing] = useState(false);

  const photoCount = photos.length + (fromWardrobe ? 1 : 0);
  const set = (key: keyof typeof form) => (text: string) => {
    setForm((current) => ({ ...current, [key]: text }));
    if (errors[key]) setErrors((current) => ({ ...current, [key]: '' }));
  };

  const pickPhotos = async () => {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      Alert.alert('Photo permission needed', 'Allow photo access to add listing photos.');
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      quality: 0.8,
      allowsMultipleSelection: true,
      selectionLimit: MAX_PHOTOS - photoCount,
    });
    if (!result.canceled) setPhotos((current) => [...current, ...result.assets].slice(0, MAX_PHOTOS - (fromWardrobe ? 1 : 0)));
  };

  const chooseWardrobeItem = (item: ClothingItem) => {
    if (fromWardrobe?.id === item.id) {
      setFromWardrobe(null);
      return;
    }
    setFromWardrobe(item);
    setPhotos((current) => current.slice(0, MAX_PHOTOS - 1));
    if (!category) setCategory(item.category);
    if (!form.title) setForm((current) => ({ ...current, title: `${item.color !== 'Unknown' ? `${item.color} ` : ''}${item.name}` }));
  };

  const publish = async () => {
    const found: Record<string, string> = {};
    const price = Number(form.price.replace(/[^\d.]/g, ''));
    if (!photoCount) found.photos = 'Add at least one photo';
    if (!form.title.trim()) found.title = 'Add a title';
    if (!price || price <= 0) found.price = 'Set a price';
    if (!category) found.category = 'Choose a category';
    if (!condition) found.condition = 'Choose the condition';
    setErrors(found);
    if (Object.keys(found).length || !category || !condition) return;
    setPublishing(true);
    try {
      const listing = await marketplaceService.createListing({
        title: form.title.trim(), price, category, condition,
        description: form.description.trim(), size: form.size.trim(), brand: form.brand.trim(),
        wardrobeItemId: fromWardrobe?.id, photos,
      });
      refreshMarketplace();
      showToast('Your item is live on the marketplace', 'success');
      navigation.replace('ProductDetail', { id: listing.id });
    } catch (error) {
      const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      showToast(typeof detail === 'string' ? detail : 'Could not publish the listing', 'error');
    } finally {
      setPublishing(false);
    }
  };

  return (
    <ScreenWrapper>
      <Header title="Sell an item" showBack onBack={() => navigation.goBack()} />
      <KeyboardAwareScroll className="px-4">
        <View className="w-full self-center pb-8" style={{ maxWidth: layout.reading }}>
          <Text className="text-text-primary font-display text-2xl mt-6 mb-1">Photos</Text>
          <Text className="text-text-secondary font-body text-sm mb-3">Up to {MAX_PHOTOS}. Show the front, back, label and any flaws.</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10 }}>
            {fromWardrobe && (
              <PhotoTile uri={fromWardrobe.imageUrl} label="From wardrobe" onRemove={() => setFromWardrobe(null)} />
            )}
            {photos.map((photo, index) => (
              <PhotoTile key={photo.uri} uri={photo.uri} onRemove={() => setPhotos((current) => current.filter((_, i) => i !== index))} />
            ))}
            {photoCount < MAX_PHOTOS && (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Add photos"
                onPress={() => void pickPhotos()}
                className={cn('w-24 h-28 rounded-sm border border-dashed items-center justify-center gap-1', errors.photos ? 'border-destructive' : 'border-border-strong')}
              >
                <Ionicons name="camera-outline" size={22} color={palette.textPrimary} />
                <Text className="text-text-secondary font-body text-xs">Add photos</Text>
              </Pressable>
            )}
          </ScrollView>
          {!!errors.photos && <Text className="text-destructive font-body text-xs mt-2">{errors.photos}</Text>}

          {!!wardrobe?.length && (
            <>
              <Text className="text-text-primary font-body-medium text-sm mt-5 mb-2">Or sell something from your wardrobe</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
                {wardrobe.map((item) => (
                  <Pressable
                    key={item.id}
                    accessibilityRole="radio"
                    accessibilityState={{ checked: fromWardrobe?.id === item.id }}
                    accessibilityLabel={item.name}
                    onPress={() => chooseWardrobeItem(item)}
                    className={cn('w-16 rounded-sm overflow-hidden border-2', fromWardrobe?.id === item.id ? 'border-primary' : 'border-transparent')}
                  >
                    <AppImage source={{ uri: item.imageUrl }} className="w-full h-20" contentFit="cover" />
                  </Pressable>
                ))}
              </ScrollView>
            </>
          )}

          <Text className="text-text-primary font-display text-2xl mt-8 mb-4">Details</Text>
          <Input label="Title" value={form.title} onChangeText={set('title')} error={errors.title} maxLength={120} />
          <View className="flex-row gap-3">
            <Input label="Price (₹)" value={form.price} onChangeText={set('price')} error={errors.price} keyboardType="number-pad" containerClassName="flex-1" />
            <Input label="Size" value={form.size} onChangeText={set('size')} hint="e.g. M, 32, UK 7" containerClassName="flex-1" maxLength={20} />
          </View>
          <Input label="Brand" value={form.brand} onChangeText={set('brand')} maxLength={60} />

          <Text className="text-text-primary font-body-medium text-sm mb-2">Category</Text>
          <View className="flex-row flex-wrap mb-1">
            {CATEGORIES.map((c) => (
              <Chip key={c.key} label={c.label} selected={category === c.key} onPress={() => { setCategory(c.key); setErrors((e) => ({ ...e, category: '' })); }} />
            ))}
          </View>
          {!!errors.category && <Text className="text-destructive font-body text-xs mb-2">{errors.category}</Text>}

          <Text className="text-text-primary font-body-medium text-sm mt-3 mb-2">Condition</Text>
          <View className="flex-row flex-wrap mb-1">
            {CONDITIONS.map((c) => (
              <Chip key={c.key} label={c.label} selected={condition === c.key} onPress={() => { setCondition(c.key); setErrors((e) => ({ ...e, condition: '' })); }} />
            ))}
          </View>
          {!!errors.condition && <Text className="text-destructive font-body text-xs mb-2">{errors.condition}</Text>}

          <Input
            label="Description"
            value={form.description}
            onChangeText={set('description')}
            multiline
            maxLength={2000}
            hint="Fit, fabric, how often it was worn, any marks"
            containerClassName="mt-4"
          />
        </View>
      </KeyboardAwareScroll>

      <View className="px-4 pb-6 pt-3 border-t border-border">
        <View className="w-full self-center" style={{ maxWidth: layout.reading }}>
          <Button size="lg" icon="pricetag-outline" label="Publish listing" loading={publishing} onPress={() => void publish()} />
        </View>
      </View>
    </ScreenWrapper>
  );
}

function PhotoTile({ uri, label, onRemove }: { uri: string; label?: string; onRemove: () => void }) {
  return (
    <View className="w-24 h-28 rounded-sm overflow-hidden">
      <AppImage source={{ uri }} className="w-full h-full" contentFit="cover" />
      {label && (
        <View className="absolute bottom-0 left-0 right-0 bg-black/55 py-0.5">
          <Text className="text-white font-body text-[10px] text-center">{label}</Text>
        </View>
      )}
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Remove photo"
        onPress={onRemove}
        hitSlop={6}
        className="absolute top-1 right-1 w-6 h-6 rounded-full bg-black/60 items-center justify-center"
      >
        <Ionicons name="close" size={14} color="#fff" />
      </Pressable>
    </View>
  );
}
