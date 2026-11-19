import { useState } from 'react';
import { View, Text, ScrollView, Pressable, useWindowDimensions } from 'react-native';
import Animated, { FadeIn, ZoomIn } from 'react-native-reanimated';
import { Ionicons } from '@expo/vector-icons';
import { EmptyState } from '@/components/shared/EmptyState';
import { useThemeColors } from '@/hooks/useThemeColors';
import { layout, motion } from '@/constants/theme';
import { cn } from '@/utils/helpers';
import { useNavigation } from '@react-navigation/native';
import { ScreenWrapper } from '@/components/shared/ScreenWrapper';
import { Header } from '@/components/shared/Header';
import { AppImage } from '@/components/shared/AppImage';
import { CompatibilityRing } from '@/components/outfits/CompatibilityRing';
import { useWardrobeStore } from '@/store/wardrobeStore';
import { calculateCompatibility } from '@/utils/helpers';
import { hapticLight } from '@/utils/haptics';

export function OutfitBuilderScreen() {
  const navigation = useNavigation();
  const items = useWardrobeStore((s) => s.items);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const toggleItem = (id: string) => {
    hapticLight();
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : prev.length < 4 ? [...prev, id] : prev,
    );
  };

  const score = selectedIds.length > 1 ? calculateCompatibility(selectedIds) : 0;

  const palette = useThemeColors();
  const { width } = useWindowDimensions();
  const columns = width >= 900 ? 5 : width >= 600 ? 4 : 3;
  const feedback =
    score >= 80
      ? 'Excellent color harmony and style match!'
      : score >= 60
        ? 'Good combo — consider adding an accessory.'
        : 'Try mixing complementary colors.';

  return (
    <ScreenWrapper>
      <Header title="Outfit builder" subtitle="Choose up to four pieces" showBack onBack={() => navigation.goBack()} />
      <ScrollView className="flex-1" contentContainerStyle={{ paddingBottom: 48 }}>
        <View className="px-4 pt-5 w-full self-center" style={{ maxWidth: layout.content }}>
          <View className="rounded-md border border-border bg-surface p-4">
            <View className="flex-row items-center justify-between mb-4">
              <Text className="text-text-primary font-body-semibold text-base">Your look</Text>
              {score > 0 ? (
                <CompatibilityRing score={score} size={56} />
              ) : (
                <Text className="text-text-tertiary font-body text-sm tabular-nums">{selectedIds.length} of 4</Text>
              )}
            </View>
            <View className="flex-row gap-2">
              {[0, 1, 2, 3].map((slot) => {
                const id = selectedIds[slot];
                const item = id ? items.find((i) => i.id === id) : undefined;
                return (
                  <View key={slot} className="flex-1">
                    {item ? (
                      <Animated.View entering={ZoomIn.duration(motion.short)}>
                        <Pressable
                          accessibilityRole="button"
                          accessibilityLabel={`Remove ${item.name}`}
                          onPress={() => toggleItem(item.id)}
                          className="aspect-[4/5] rounded-sm overflow-hidden border border-border-strong"
                        >
                          <AppImage source={{ uri: item.imageUrl }} className="w-full h-full" contentFit="cover" />
                          <View className="absolute top-1.5 right-1.5 w-6 h-6 rounded-full bg-background/80 items-center justify-center">
                            <Ionicons name="close" size={13} color={palette.textPrimary} />
                          </View>
                        </Pressable>
                      </Animated.View>
                    ) : (
                      <View
                        className="aspect-[4/5] rounded-sm border border-dashed border-border-strong items-center justify-center"
                        accessibilityLabel={`Empty slot ${slot + 1}`}
                      >
                        <Ionicons name="add" size={20} color={palette.textTertiary} />
                      </View>
                    )}
                  </View>
                );
              })}
            </View>
            <View className="mt-4 pt-4 border-t border-border min-h-12 justify-center" accessibilityLiveRegion="polite">
              {score > 0 ? (
                <Animated.View key={feedback} entering={FadeIn.duration(motion.short)} className="flex-row items-center gap-2">
                  <Ionicons name="sparkles-outline" size={16} color={palette.accent} />
                  <Text className="text-text-primary font-body text-sm flex-1">{feedback}</Text>
                </Animated.View>
              ) : (
                <Text className="text-text-secondary font-body text-sm">
                  {selectedIds.length === 1 ? 'Add one more piece to see how they work together.' : 'Tap pieces below to start a look.'}
                </Text>
              )}
            </View>
          </View>

          <Text className="text-text-primary font-display text-2xl mt-8 mb-4">Your wardrobe</Text>
          {items.length === 0 ? (
            <View className="min-h-[360px]">
              <EmptyState title="Nothing to style yet" message="Add pieces to your wardrobe, then come back to build a look." />
            </View>
          ) : (
            <View className="flex-row flex-wrap -mx-1">
              {items.map((item) => {
                const selected = selectedIds.includes(item.id);
                const full = !selected && selectedIds.length >= 4;
                return (
                  <Pressable
                    key={item.id}
                    accessibilityRole="checkbox"
                    accessibilityState={{ checked: selected, disabled: full }}
                    accessibilityLabel={`Select ${item.name}`}
                    onPress={() => toggleItem(item.id)}
                    className="p-1 mb-2"
                    style={{ width: `${100 / columns}%` }}
                  >
                    <View
                      className={cn(
                        'aspect-[4/5] rounded-sm overflow-hidden border-2',
                        selected ? 'border-primary' : 'border-transparent',
                        full && 'opacity-40',
                      )}
                    >
                      <AppImage source={{ uri: item.imageUrl }} className="w-full h-full" contentFit="cover" />
                      {selected && (
                        <View className="absolute top-1.5 right-1.5 w-6 h-6 rounded-full bg-primary items-center justify-center">
                          <Ionicons name="checkmark" size={14} color={palette.primaryInk} />
                        </View>
                      )}
                    </View>
                    <Text className="text-text-secondary font-body text-xs mt-1.5" numberOfLines={1}>
                      {item.name}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
          )}
        </View>
      </ScrollView>
    </ScreenWrapper>
  );
}
