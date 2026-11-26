import { useState } from 'react';
import { View, Text, FlatList, TextInput, Pressable, RefreshControl } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { ScreenWrapper } from '@/components/shared/ScreenWrapper';
import { EmptyState } from '@/components/shared/EmptyState';
import { ProductCard } from '@/components/marketplace/ProductCard';
import { Chip } from '@/components/ui/Chip';
import { Button } from '@/components/ui/Button';
import { MARKETPLACE_CATEGORIES } from '@/constants/categories';
import { useConversations, useProducts } from '@/hooks';
import { useThemeColors } from '@/hooks/useThemeColors';
import { useAuthStore } from '@/store/authStore';
import { useCartStore } from '@/store/cartStore';
import type { ClothingCategory } from '@/types';

export function MarketplaceScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<Record<string, object | undefined>>>();
  const { data: products, isLoading, isError, refetch, isRefetching } = useProducts();
  const { data: inbox } = useConversations();
  const myId = useAuthStore((s) => s.user?.id);
  const bagCount = useCartStore((s) => s.items.length);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState<ClothingCategory | 'all' | 'trending'>('all');
  const palette = useThemeColors();

  const query = search.trim().toLowerCase();
  const filtered = (products ?? []).filter((p) => {
    if (category !== 'all' && category !== 'trending' && p.category !== category) return false;
    if (category === 'trending' && !p.isNew) return false;
    if (query && ![p.title, p.brand, p.description].some((text) => text.toLowerCase().includes(query))) return false;
    return true;
  });

  return (
    <ScreenWrapper loading={isLoading} error={isError ? 'Failed to load the marketplace' : null} onRetry={refetch}>
      <View className="px-4 pt-3">
        <View className="flex-row items-center justify-between mb-4 px-1">
          <Pressable accessibilityRole="button" accessibilityLabel="Go back" onPress={() => navigation.goBack()} hitSlop={8} className="mr-2">
            <Ionicons name="chevron-back" size={24} color={palette.textPrimary} />
          </Pressable>
          <Text accessibilityRole="header" className="flex-1 text-text-primary font-display text-4xl tracking-tight">Marketplace</Text>
          <HeaderIcon icon="chatbubbles-outline" label="Messages" count={inbox?.unread ?? 0} onPress={() => navigation.navigate('Messages')} />
          <HeaderIcon icon="bag-outline" label="Your bag" count={bagCount} onPress={() => navigation.navigate('Cart')} />
        </View>
        <View className="flex-row items-center gap-2 mb-3">
          <View className="flex-1 flex-row items-center bg-surface rounded-sm border border-border px-3 h-12">
            <Ionicons name="search" size={17} color={palette.textTertiary} />
            <TextInput
              accessibilityLabel="Search marketplace"
              value={search}
              onChangeText={setSearch}
              placeholder="Search pieces, brands"
              placeholderTextColor={palette.textTertiary}
              selectionColor={palette.accent}
              className="flex-1 h-full px-2 text-text-primary font-body text-base"
            />
          </View>
          <Button label="Sell" icon="add" onPress={() => navigation.navigate('SellItem')} />
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
          style={{ flexGrow: 0 }}
        />
      </View>

      <FlatList
        data={filtered}
        numColumns={2}
        keyExtractor={(item) => item.id}
        contentContainerClassName="px-3 pb-8"
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={palette.accent} />}
        ListEmptyComponent={
          <View className="min-h-[360px]">
            <EmptyState
              icon="storefront-outline"
              title={products?.length ? 'Nothing matches' : 'No listings yet'}
              message={products?.length ? 'Try another search or category.' : 'Be the first to sell a piece you no longer wear.'}
              actionLabel={products?.length ? undefined : 'Sell an item'}
              onAction={products?.length ? undefined : () => navigation.navigate('SellItem')}
            />
          </View>
        }
        renderItem={({ item }) => (
          <ProductCard
            product={item}
            onPress={() => navigation.navigate('ProductDetail', { id: item.id })}
            className={item.seller.id === myId ? 'opacity-90' : undefined}
          />
        )}
      />
    </ScreenWrapper>
  );
}

function HeaderIcon({
  icon,
  label,
  count,
  onPress,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  count: number;
  onPress: () => void;
}) {
  const palette = useThemeColors();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={count ? `${label}, ${count} new` : label}
      onPress={onPress}
      className="w-11 h-11 items-center justify-center"
    >
      <Ionicons name={icon} size={23} color={palette.textPrimary} />
      {count > 0 && (
        <View className="absolute top-1 right-1 min-w-[18px] h-[18px] px-1 rounded-full bg-accent items-center justify-center">
          <Text className="text-primary-ink font-body-semibold text-[10px] tabular-nums">{count > 9 ? '9+' : count}</Text>
        </View>
      )}
    </Pressable>
  );
}
