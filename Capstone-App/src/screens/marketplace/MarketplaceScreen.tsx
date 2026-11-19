import { useState } from 'react';
import { useThemeColors } from '@/hooks/useThemeColors';
import { View, Text, FlatList, TextInput, Pressable, RefreshControl } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { ScreenWrapper } from '@/components/shared/ScreenWrapper';
import { ProductCard } from '@/components/marketplace/ProductCard';
import { Chip } from '@/components/ui/Chip';
import { MARKETPLACE_CATEGORIES } from '@/constants/categories';
import { useProducts } from '@/hooks';
import type { ClothingCategory } from '@/types';

export function MarketplaceScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<Record<string, object | undefined>>>();
  const { data: products, isLoading, isError, refetch } = useProducts();
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState<ClothingCategory | 'all' | 'trending'>('all');
  const palette = useThemeColors();

  const filtered = (products ?? []).filter((p) => {
    if (category !== 'all' && category !== 'trending' && p.category !== category) return false;
    if (category === 'trending' && !p.isNew) return false;
    if (search && !p.title.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  return (
    <ScreenWrapper loading={isLoading} error={isError ? 'Failed to load products' : null} onRetry={refetch} empty={!filtered.length} emptyTitle="No products found" emptyMessage="Try adjusting your filters">
      <View className="px-4 pt-3">
        <Text accessibilityRole="header" className="text-text-primary font-display text-4xl tracking-tight mb-4 px-1">Marketplace</Text>
        <View className="flex-row items-center gap-2 mb-3">
          <View className="flex-1 flex-row items-center bg-surface rounded-sm border border-border px-3 h-12">
            <Ionicons name="search" size={17} color={palette.textTertiary} />
            <TextInput
              accessibilityLabel="Search marketplace"
              value={search}
              onChangeText={setSearch}
              placeholder="Search pieces"
              placeholderTextColor={palette.textTertiary}
              selectionColor={palette.accent}
              className="flex-1 h-full px-2 text-text-primary font-body text-base"
            />
          </View>
          <Pressable accessibilityRole="button" accessibilityLabel="Filter marketplace" className="w-12 h-12 items-center justify-center bg-surface rounded-sm border border-border">
            <Ionicons name="options-outline" size={19} color={palette.textPrimary} />
          </Pressable>
        </View>
        <FlatList
          horizontal
          data={MARKETPLACE_CATEGORIES}
          keyExtractor={(item) => item.key}
          showsHorizontalScrollIndicator={false}
          renderItem={({ item }) => (
            <Chip label={item.label} selected={category === item.key} onPress={() => setCategory(item.key)} />
          )}
          className="mb-2"
        />
      </View>

      <FlatList
        data={filtered}
        numColumns={2}
        keyExtractor={(item) => item.id}
        contentContainerClassName="px-3 pb-8"
        refreshControl={<RefreshControl refreshing={isLoading} onRefresh={refetch} tintColor={palette.accent} />}
        renderItem={({ item }) => (
          <ProductCard product={item} onPress={() => navigation.navigate('ProductDetail', { id: item.id })} />
        )}
      />
    </ScreenWrapper>
  );
}
