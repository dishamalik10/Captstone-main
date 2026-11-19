import { View, Text, ScrollView, Alert, Platform, Pressable, useWindowDimensions } from 'react-native';
import Animated, { FadeIn, FadeInDown } from 'react-native-reanimated';
import { Ionicons } from '@expo/vector-icons';
import { GradientScrim } from '@/components/shared/GradientScrim';
import { useThemeColors } from '@/hooks/useThemeColors';
import { landing, layout, motion, withAlpha } from '@/constants/theme';
import { cn } from '@/utils/helpers';
import { useRoute, useNavigation } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { ScreenWrapper } from '@/components/shared/ScreenWrapper';
import { AppImage } from '@/components/shared/AppImage';
import { Button } from '@/components/ui/Button';
import { useWardrobeStore } from '@/store/wardrobeStore';
import { useToastStore } from '@/components/ui/Toast';
import { useAuthStore } from '@/store/authStore';
import { wardrobeService } from '@/services';
import { CLOTHING_CATEGORIES } from '@/constants/categories';
import type { ClothingCategory } from '@/types';

export function ClothingDetailScreen() {
  const route = useRoute<RouteProp<{ params: { id: string } }>>();
  const navigation = useNavigation<NativeStackNavigationProp<Record<string, object | undefined>>>();
  const { id } = route.params;
  const item = useWardrobeStore((s) => s.items.find((i) => i.id === id));
  const { removeItem, incrementWearCount, updateItem } = useWardrobeStore();
  const showToast = useToastStore((s) => s.show);
  const userId = useAuthStore((s) => s.user?.id) ?? 'demo-user';
  const palette = useThemeColors();
  const { width, height } = useWindowDimensions();

  if (!item) {
    return <ScreenWrapper error="Item not found" onRetry={() => navigation.goBack()} />;
  }

  const performDelete = async () => {
    try {
      await wardrobeService.deleteItem(userId, id);
      removeItem(id);
      showToast('Item deleted', 'success');
      navigation.goBack();
    } catch {
      showToast('Could not delete item', 'error');
    }
  };

  const handleDelete = () => {
    if (Platform.OS === 'web') {
      if (globalThis.confirm?.(`Delete ${item.name}? This cannot be undone.`)) {
        void performDelete();
      }
      return;
    }
    Alert.alert('Delete Item', 'Are you sure?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: () => void performDelete(),
      },
    ]);
  };

  const correctCategory = async (category: ClothingCategory) => {
    try {
      const updated = await wardrobeService.updateItem(userId, id, { category });
      updateItem(id, updated);
      showToast(`Category changed to ${category}`, 'success');
    } catch {
      showToast('Could not update category', 'error');
    }
  };

  const imageHeight = Math.min(height * 0.62, width * 1.25, 680);
  const attributes: [string, string][] = [
    ['Category', item.category],
    ['Colour', item.color],
    ['Pattern', item.pattern],
    ['Season', item.season],
    ['Brand', item.brand],
  ];

  return (
    <ScreenWrapper>
      <ScrollView className="flex-1" contentContainerStyle={{ paddingBottom: 48 }} showsVerticalScrollIndicator={false}>
        <View style={{ height: imageHeight, maxWidth: layout.reading }} className="w-full self-center overflow-hidden bg-surface-raised">
          <Animated.View entering={FadeIn.duration(motion.long)} className="w-full h-full">
            <AppImage source={{ uri: item.imageUrl }} className="w-full h-full" contentFit="cover" accessibilityLabel={item.name} />
          </Animated.View>
          <GradientScrim color={palette.background} opacity={0.9} from={0.6} />
        </View>

        <Animated.View entering={FadeInDown.duration(motion.long).delay(60)} className="px-5 -mt-8 w-full self-center" style={{ maxWidth: layout.reading }}>
          <View className="flex-row items-center gap-2 mb-2">
            <View className="w-3.5 h-3.5 rounded-full border border-border-strong" style={{ backgroundColor: item.colorHex }} />
            <Text className="text-text-secondary font-body text-sm capitalize">{item.category}</Text>
          </View>
          <Text accessibilityRole="header" className="text-text-primary font-display text-4xl tracking-tight">{item.name}</Text>
          <Text className="text-text-secondary font-body text-sm mt-2 tabular-nums">
            Worn {item.wearCount} {item.wearCount === 1 ? 'time' : 'times'}
            {item.lastWorn ? `, last on ${item.lastWorn}` : ''}
          </Text>

          <View className="mt-6 border-t border-text-primary">
            {attributes.map(([k, v]) => (
              <View key={k} className="flex-row justify-between items-center py-3 border-b border-border">
                <Text className="text-text-secondary font-body text-sm">{k}</Text>
                <Text className="text-text-primary font-body-medium text-base capitalize">{v}</Text>
              </View>
            ))}
          </View>

          <View className="flex-row gap-3 mt-8">
            <View className="flex-1">
              <Button label="Create outfit" icon="sparkles-outline" onPress={() => navigation.navigate('OutfitBuilder')} />
            </View>
            <View className="flex-1">
              <Button
                variant="secondary"
                label="Wear today"
                icon="checkmark"
                onPress={() => {
                  incrementWearCount(id);
                  showToast('Logged to wear history', 'success');
                }}
              />
            </View>
          </View>

          <Text className="text-text-primary font-display text-xl mt-10 mb-1">Correct the category</Text>
          <Text className="text-text-secondary font-body text-sm mb-4">
            If AURA labelled this piece wrongly, choose the right category.
          </Text>
          <View className="flex-row flex-wrap gap-2 mb-10">
            {CLOTHING_CATEGORIES.filter((category) => category.key !== 'all').map((category) => {
              const selected = item.category === category.key;
              return (
                <Pressable
                  key={category.key}
                  accessibilityRole="radio"
                  accessibilityState={{ checked: selected }}
                  accessibilityLabel={category.label}
                  onPress={() => void correctCategory(category.key as ClothingCategory)}
                  className={cn(
                    'min-h-10 px-4 rounded-full border justify-center',
                    selected ? 'border-primary bg-primary' : 'border-border bg-transparent hover:border-border-strong',
                  )}
                >
                  <Text className={cn('text-sm', selected ? 'text-primary-ink font-body-medium' : 'text-text-secondary font-body')}>
                    {category.label}
                  </Text>
                </Pressable>
              );
            })}
          </View>

          <Button variant="destructive" label="Delete from wardrobe" icon="trash-outline" onPress={handleDelete} />
        </Animated.View>
      </ScrollView>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Go back"
        onPress={() => navigation.goBack()}
        className="absolute top-3 left-4 w-11 h-11 rounded-full items-center justify-center"
        style={{ backgroundColor: withAlpha(landing.night, 0.55) }}
      >
        <Ionicons name="chevron-back" size={20} color={landing.inkPaper} />
      </Pressable>
    </ScreenWrapper>
  );
}
