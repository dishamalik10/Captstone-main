import { useState, useRef, useEffect, useMemo } from 'react';
import { View, Text, FlatList, Pressable, TextInput, Alert, ActivityIndicator, useWindowDimensions } from 'react-native';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import BottomSheet from '@gorhom/bottom-sheet';
import * as ImagePicker from 'expo-image-picker';
import { Ionicons } from '@expo/vector-icons';
import { ScreenWrapper } from '@/components/shared/ScreenWrapper';
import { EmptyState } from '@/components/shared/EmptyState';
import { ClothingCard } from '@/components/wardrobe/ClothingCard';
import { CategoryPill } from '@/components/wardrobe/CategoryPill';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Chip } from '@/components/ui/Chip';
import { AppBottomSheet } from '@/components/ui/BottomSheet';
import { useWardrobeStore } from '@/store/wardrobeStore';
import { useAuthStore } from '@/store/authStore';
import { wardrobeService } from '@/services';
import { useWardrobeItems } from '@/hooks';
import { useToastStore } from '@/components/ui/Toast';
import { COLORS_FILTER, SEASONS } from '@/constants/categories';
import type { ClothingCategory } from '@/types';
import { hapticLight } from '@/utils/haptics';
import { cn } from '@/utils/helpers';
import { SkeletonGrid } from '@/components/ui/Skeleton';
import { useThemeColors } from '@/hooks/useThemeColors';
import { motion } from '@/constants/theme';

export function WardrobeScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<Record<string, object | undefined>>>();
  const allItems = useWardrobeStore((s) => s.items);
  const { filters, setFilters, addItem, removeItem, updateItem, setItems } = useWardrobeStore();
  const userId = useAuthStore((s) => s.user?.id) ?? 'demo-user';
  const wardrobeQuery = useWardrobeItems();
  const showToast = useToastStore((s) => s.show);
  const filterSheetRef = useRef<BottomSheet>(null);
  const uploadSheetRef = useRef<BottomSheet>(null);
  const [search, setSearch] = useState('');
  const [analyzing, setAnalyzing] = useState(false);
  const [pendingItemId, setPendingItemId] = useState<string | null>(null);
  const [uploadForm, setUploadForm] = useState({ name: '', category: 'tops', color: 'White', pattern: 'Solid', season: 'all', brand: '' });
  const palette = useThemeColors();
  const { width } = useWindowDimensions();
  const columns = width >= 1024 ? 4 : width >= 720 ? 3 : 2;
  const activeFilters = [filters.color, filters.season].filter(Boolean).length;

  useEffect(() => {
    if (wardrobeQuery.data) setItems(wardrobeQuery.data);
  }, [wardrobeQuery.data, setItems]);

  const items = useMemo(() => {
    return allItems.filter((item) => {
      const f = { ...filters, search };
      if (f.category && f.category !== 'all' && item.category !== f.category) return false;
      if (f.color && item.color.toLowerCase() !== f.color.toLowerCase()) return false;
      if (f.season && item.season !== f.season) return false;
      if (f.brand && !item.brand.toLowerCase().includes(f.brand.toLowerCase())) return false;
      if (f.search) {
        const q = f.search.toLowerCase();
        return item.name.toLowerCase().includes(q) || item.brand.toLowerCase().includes(q) || item.color.toLowerCase().includes(q);
      }
      return true;
    });
  }, [search, filters, allItems]);

  const deleteItem = async (id: string) => {
    try {
      await wardrobeService.deleteItem(userId, id);
      removeItem(id);
      showToast('Item deleted', 'success');
    } catch {
      showToast('Could not delete item', 'error');
    }
  };

  const handleLongPress = (id: string, name: string) => {
    Alert.alert(name, 'Choose an action', [
      { text: 'Edit', onPress: () => navigation.navigate('ClothingDetail', { id }) },
      { text: 'Delete', style: 'destructive', onPress: () => void deleteItem(id) },
      { text: 'Add to Outfit', onPress: () => navigation.navigate('OutfitBuilder') },
      { text: 'Cancel', style: 'cancel' },
    ]);
  };

  const pickImage = async (useCamera: boolean) => {
    if (useCamera) {
      const permission = await ImagePicker.requestCameraPermissionsAsync();
      if (!permission.granted) {
        Alert.alert('Camera permission needed', 'Allow camera access to photograph a wardrobe item.');
        return;
      }
    } else {
      const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!permission.granted) {
        Alert.alert('Photo permission needed', 'Allow photo access to choose a wardrobe item.');
        return;
      }
    }
    const fn = useCamera ? ImagePicker.launchCameraAsync : ImagePicker.launchImageLibraryAsync;
    const result = await fn({ mediaTypes: ['images'], quality: 0.8 });
    if (!result.canceled) {
      try {
        setAnalyzing(true);
        const uploaded = await wardrobeService.upload(userId, result.assets[0]);
        addItem(uploaded);
        setPendingItemId(uploaded.id);
        setUploadForm({
          name: uploaded.name,
          category: uploaded.category,
          color: uploaded.color,
          pattern: uploaded.pattern,
          season: uploaded.season,
          brand: uploaded.brand,
        });
        showToast(
          uploaded.needsReview ? 'CNN prediction ready—please review it' : 'CNN identified and saved your item',
          'success',
        );
      } catch {
        showToast('Upload failed. Check that the backend is running.', 'error');
      } finally {
        setAnalyzing(false);
      }
    }
  };

  const saveItem = async () => {
    if (!pendingItemId) {
      showToast('Choose or photograph an item first', 'error');
      return;
    }
    try {
      const item = await wardrobeService.updateItem(userId, pendingItemId, {
        name: uploadForm.name,
        category: uploadForm.category as ClothingCategory,
        color: uploadForm.color,
        pattern: uploadForm.pattern,
        season: uploadForm.season as 'spring' | 'summer' | 'fall' | 'winter' | 'all',
      });
      updateItem(pendingItemId, item);
      setPendingItemId(null);
      setUploadForm({ name: '', category: 'tops', color: 'White', pattern: 'Solid', season: 'all', brand: '' });
      uploadSheetRef.current?.close();
      showToast('Wardrobe item confirmed', 'success');
    } catch {
      showToast('Could not save corrections', 'error');
    }
  };

  return (
    <ScreenWrapper>
      <View className="px-4 pt-3 pb-2">
        <View className="flex-row items-end justify-between mb-4 px-1">
          <View>
            <Text accessibilityRole="header" className="text-text-primary font-display text-4xl tracking-tight">
              Wardrobe
            </Text>
            <Text className="text-text-secondary font-body text-sm mt-1 tabular-nums">
              {allItems.length} {allItems.length === 1 ? 'piece' : 'pieces'}
              {items.length !== allItems.length ? `, ${items.length} shown` : ''}
            </Text>
          </View>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Add another clothing item"
            onPress={() => uploadSheetRef.current?.expand()}
            className="h-11 px-4 flex-row items-center justify-center bg-primary rounded-sm gap-1.5"
          >
            <Ionicons name="add" size={18} color={palette.primaryInk} />
            <Text className="text-primary-ink font-body-semibold text-sm">Add item</Text>
          </Pressable>
        </View>
        <View className="flex-row items-center gap-2">
          <View className="flex-1 flex-row items-center bg-surface rounded-sm border border-border px-3 h-12">
            <Ionicons name="search" size={17} color={palette.textTertiary} />
            <TextInput
              accessibilityLabel="Search wardrobe"
              value={search}
              onChangeText={setSearch}
              placeholder="Search name, colour, brand"
              placeholderTextColor={palette.textTertiary}
              selectionColor={palette.accent}
              className="flex-1 h-full px-2 text-text-primary font-body text-base"
            />
            {!!search && (
              <Pressable accessibilityRole="button" accessibilityLabel="Clear search" onPress={() => setSearch('')} hitSlop={10}>
                <Ionicons name="close-circle" size={18} color={palette.textTertiary} />
              </Pressable>
            )}
          </View>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={activeFilters ? `Filter wardrobe, ${activeFilters} active` : 'Filter wardrobe'}
            onPress={() => filterSheetRef.current?.expand()}
            className={cn(
              'h-12 px-3.5 flex-row items-center justify-center rounded-sm border gap-1.5',
              activeFilters ? 'border-text-primary bg-surface' : 'border-border bg-surface',
            )}
          >
            <Ionicons name="options-outline" size={19} color={palette.textPrimary} />
            {activeFilters > 0 && (
              <Text className="text-text-primary font-body-semibold text-sm tabular-nums">{activeFilters}</Text>
            )}
          </Pressable>
        </View>
      </View>

      <CategoryPill
        selected={filters.category ?? 'all'}
        onSelect={(cat) => setFilters({ category: cat })}
      />

      {wardrobeQuery.isLoading && !allItems.length ? (
        <View className="pt-2">
          <SkeletonGrid count={6} />
        </View>
      ) : (
        <FlatList
          key={`grid-${columns}`}
          data={items}
          numColumns={columns}
          keyExtractor={(item) => item.id}
          contentContainerClassName="px-3 pt-2 pb-32"
          showsVerticalScrollIndicator={false}
          ListEmptyComponent={
            <View className="flex-1 min-h-[460px]">
              <EmptyState
                icon={search || activeFilters ? 'search-outline' : 'shirt-outline'}
                title={search || activeFilters ? 'No matching pieces' : 'Your wardrobe starts here'}
                message={
                  search || activeFilters
                    ? 'Try another search or clear your filters.'
                    : 'Photograph a few things you wear often. AURA will tag them and start styling.'
                }
                actionLabel={search || activeFilters ? undefined : 'Add your first piece'}
                onAction={search || activeFilters ? undefined : () => uploadSheetRef.current?.expand()}
              />
            </View>
          }
          renderItem={({ item, index }) => (
            <Animated.View
              entering={index < 12 ? FadeInDown.duration(motion.long).delay(index * 40) : undefined}
              className={cn('w-1/2', columns === 3 && 'w-1/3', columns === 4 && 'w-1/4')}
            >
              <ClothingCard
                item={item}
                className="w-auto max-w-none"
                onPress={() => navigation.navigate('ClothingDetail', { id: item.id })}
                onLongPress={() => handleLongPress(item.id, item.name)}
              />
            </Animated.View>
          )}
        />
      )}

      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Add clothing item"
        onPress={() => {
          hapticLight();
          uploadSheetRef.current?.expand();
        }}
        className="absolute bottom-24 right-5 w-14 h-14 rounded-full bg-primary items-center justify-center"
        style={{ shadowColor: palette.scrim, shadowOpacity: 0.25, shadowRadius: 12, shadowOffset: { width: 0, height: 6 }, elevation: 6 }}
      >
        <Ionicons name="add" size={26} color={palette.primaryInk} />
      </Pressable>

      <AppBottomSheet ref={filterSheetRef} title="Filter">
        <Text className="text-text-primary font-body-semibold text-base mb-3">Colour</Text>
        <View className="flex-row flex-wrap mb-6">
          {COLORS_FILTER.map((c) => (
            <Chip key={c} label={c} selected={filters.color === c} onPress={() => setFilters({ color: filters.color === c ? undefined : c })} />
          ))}
        </View>
        <Text className="text-text-primary font-body-semibold text-base mb-3">Season</Text>
        <View className="flex-row flex-wrap mb-8">
          {SEASONS.map((s) => (
            <Chip key={s} label={s.charAt(0).toUpperCase() + s.slice(1)} selected={filters.season === s} onPress={() => setFilters({ season: filters.season === s ? undefined : s })} />
          ))}
        </View>
        <View className="flex-row gap-3">
          <Button
            variant="secondary"
            label="Clear all"
            disabled={!activeFilters}
            onPress={() => setFilters({ color: undefined, season: undefined })}
            className="flex-1"
          />
          <Button label="Show results" onPress={() => filterSheetRef.current?.close()} className="flex-1" />
        </View>
      </AppBottomSheet>

      <AppBottomSheet ref={uploadSheetRef} title="Add to wardrobe" snapPoints={['72%', '92%']}>
        {analyzing ? (
          <View className="items-center py-16" accessibilityLiveRegion="polite">
            <ActivityIndicator color={palette.accent} />
            <Text className="text-text-primary font-display text-xl mt-5">Reading your piece</Text>
            <Text className="text-text-secondary font-body text-sm mt-1 text-center">
              Identifying category, colour and pattern.
            </Text>
          </View>
        ) : (
          <>
            <Text className="text-text-secondary font-body text-sm mb-4">
              Photograph one piece on a plain background for the best result.
            </Text>
            <View className="flex-row gap-3 mb-6">
              <UploadOption icon="camera-outline" label="Take photo" onPress={() => pickImage(true)} />
              <UploadOption icon="images-outline" label="From library" onPress={() => pickImage(false)} />
            </View>
            {pendingItemId && (
              <View className="flex-row items-center gap-2 mb-4 p-3 rounded-sm bg-surface-raised">
                <Ionicons name="sparkles-outline" size={16} color={palette.accent} />
                <Text className="text-text-primary font-body text-sm flex-1">Check the details AURA detected, then save.</Text>
              </View>
            )}
            <Input label="Name" value={uploadForm.name} onChangeText={(t) => setUploadForm((f) => ({ ...f, name: t }))} />
            <Input label="Brand" value={uploadForm.brand} onChangeText={(t) => setUploadForm((f) => ({ ...f, brand: t }))} />
            <Input label="Category" value={uploadForm.category} onChangeText={(t) => setUploadForm((f) => ({ ...f, category: t }))} />
            <Input label="Colour" value={uploadForm.color} onChangeText={(t) => setUploadForm((f) => ({ ...f, color: t }))} />
            <Button label="Save to wardrobe" size="lg" onPress={saveItem} className="mt-2" />
          </>
        )}
      </AppBottomSheet>
    </ScreenWrapper>
  );
}

function UploadOption({
  icon,
  label,
  onPress,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  onPress: () => void;
}) {
  const palette = useThemeColors();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={() => {
        hapticLight();
        onPress();
      }}
      className="flex-1 h-28 rounded-md border border-border bg-surface-raised items-center justify-center gap-2 hover:border-border-strong"
    >
      <Ionicons name={icon} size={26} color={palette.textPrimary} />
      <Text className="text-text-primary font-body-medium text-sm">{label}</Text>
    </Pressable>
  );
}
