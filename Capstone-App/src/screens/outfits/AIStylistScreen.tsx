import { useEffect, useRef, useState } from 'react';
import { View, Text, Pressable, ScrollView, useWindowDimensions } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  runOnJS,
  interpolate,
  Extrapolation,
  FadeIn,
} from 'react-native-reanimated';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { ScreenWrapper } from '@/components/shared/ScreenWrapper';
import { AppImage } from '@/components/shared/AppImage';
import { OutfitCollage } from '@/components/outfits/OutfitCollage';
import { Chip } from '@/components/ui/Chip';
import { Button } from '@/components/ui/Button';
import { OCCASIONS } from '@/constants/categories';
import { useOutfitAI, useOutfitRecommendations, useWeather } from '@/hooks';
import { useToastStore } from '@/components/ui/Toast';
import { useWardrobeStore } from '@/store/wardrobeStore';
import type { Occasion, Outfit } from '@/types';
import { hapticLight, hapticMedium } from '@/utils/haptics';
import { cn } from '@/utils/helpers';
import { GradientScrim } from '@/components/shared/GradientScrim';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { StylistNote } from '@/components/outfits/StylistNote';
import { useThemeColors } from '@/hooks/useThemeColors';
import { landing, motion } from '@/constants/theme';

export function AIStylistScreen() {
  const navigation = useNavigation();
  const [occasion, setOccasion] = useState<Occasion>('casual');
  const { data: outfits, isLoading, isError, error, refetch } = useOutfitRecommendations(occasion);
  const { data: weather } = useWeather();
  const showToast = useToastStore((s) => s.show);
  const { feedbackMutation, alternativesMutation } = useOutfitAI();
  const [deck, setDeck] = useState<Outfit[] | null>(null);
  const seenRecommendationIds = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (outfits) {
      setDeck(outfits);
      seenRecommendationIds.current = new Set(outfits.map((outfit) => outfit.id));
    }
  }, [outfits, occasion]);

  const currentOutfits = deck ?? outfits ?? [];
  const palette = useThemeColors();
  const { width } = useWindowDimensions();
  const cardWidth = Math.min(width - 32, 520);

  const handleAction = async (action: 'skip' | 'like' | 'dislike' | 'save' | 'wear') => {
    const current = currentOutfits[0];
    if (!current) return;
    hapticMedium();
    try {
      await feedbackMutation.mutateAsync({ outfit: current, action });
      const messages = {
        skip: 'Skipped—your taste profile was updated',
        like: 'Liked—future outfits will use this signal',
        dislike: 'Disliked—future outfits will use this signal',
        save: 'Outfit saved!',
        wear: 'Marked as worn today',
      };
      const msg = messages[action];
      showToast(msg, 'success');
      setDeck(currentOutfits.slice(1));
    } catch {
      showToast('Could not save your feedback', 'error');
    }
  };

  const handleAlternatives = async () => {
    const excludeRecommendationIds = [...seenRecommendationIds.current];
    try {
      const alternatives = await alternativesMutation.mutateAsync({
        occasion,
        excludeRecommendationIds,
        temperature: weather?.temperature,
        condition: weather?.condition,
      });
      if (!alternatives.length) {
        showToast('No distinct combinations remain for this occasion', 'info');
        return;
      }
      alternatives.forEach((outfit) => seenRecommendationIds.current.add(outfit.id));
      setDeck(alternatives);
      showToast('Showing different wardrobe combinations', 'success');
    } catch (requestError) {
      const detail = (requestError as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      showToast(detail ?? 'Could not find another distinct outfit', 'error');
    }
  };

  return (
    <ScreenWrapper
      error={isError
        ? ((error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
          ?? 'Failed to load recommendations')
        : null}
      onRetry={refetch}
    >
      <ScrollView contentContainerStyle={{ paddingBottom: 120 }} showsVerticalScrollIndicator={false}>
        <View className="px-5 pt-3">
          <View className="flex-row items-end justify-between">
            <View className="flex-1 pr-3">
              <Text accessibilityRole="header" className="text-text-primary font-display text-4xl tracking-tight">
                Stylist
              </Text>
              <Text className="text-text-secondary font-body text-sm mt-1">Outfits from your wardrobe, for where you’re going.</Text>
            </View>
            {weather && (
              <View className="flex-row items-center gap-1.5 px-3 h-8 rounded-full border border-border mb-1">
                <Ionicons name="partly-sunny-outline" size={15} color={palette.accent} />
                <Text className="text-text-primary font-body-medium text-sm tabular-nums">{weather.temperature}°C</Text>
                <Text className="text-text-secondary font-body text-sm">{weather.condition}</Text>
              </View>
            )}
          </View>
        </View>

        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={{ flexGrow: 0 }}
          contentContainerStyle={{ paddingHorizontal: 20, paddingTop: 20, paddingBottom: 12 }}
          accessibilityRole="radiogroup"
        >
          {OCCASIONS.map((o) => (
            <Chip
              key={o.key}
              label={o.label}
              icon={o.icon as keyof typeof Ionicons.glyphMap}
              selected={occasion === o.key}
              onPress={() => setOccasion(o.key)}
            />
          ))}
        </ScrollView>

        <View className="items-center px-4 pt-2" style={{ minHeight: 420 }}>
          {isLoading ? (
            <View style={{ width: cardWidth }}>
              <SkeletonCard />
            </View>
          ) : !currentOutfits.length ? (
            <Animated.View entering={FadeIn.duration(motion.long)} className="items-center px-6 py-16" style={{ maxWidth: 420 }}>
              <View className="w-20 h-20 rounded-full border border-border items-center justify-center mb-5">
                <Ionicons name="shirt-outline" size={28} color={palette.accent} />
              </View>
              <Text className="text-text-primary font-display text-2xl text-center">That’s every outfit for now</Text>
              <Text className="text-text-secondary font-body text-base text-center mt-2">
                Try another occasion, or ask for combinations that haven’t appeared yet.
              </Text>
            </Animated.View>
          ) : currentOutfits.slice(0, 3).map((outfit, index) => (
            <SwipeCard
              key={outfit.id}
              outfit={outfit}
              index={index}
              width={cardWidth}
              onSkip={() => void handleAction('skip')}
              onLike={() => void handleAction('like')}
              onDislike={() => void handleAction('dislike')}
              onSave={() => void handleAction('save')}
              onWear={() => void handleAction('wear')}
            />
          ))}
          {!isLoading && currentOutfits.length > 0 && (
            <Text className="text-text-tertiary font-body text-xs mt-3 text-center">
              Swipe right to save, left to skip.
            </Text>
          )}
        </View>

        <View className="px-4 pt-6 gap-3 self-center w-full" style={{ maxWidth: 552 }}>
          <Button
            variant="secondary"
            icon="shuffle"
            label={alternativesMutation.isPending ? 'Finding alternatives…' : 'Show different combinations'}
            loading={alternativesMutation.isPending}
            onPress={() => void handleAlternatives()}
          />
          {currentOutfits[0] && (
            <Button
              icon="person-circle-outline"
              label="Try it on me"
              onPress={() => (navigation as unknown as { navigate: (name: string, params: object) => void })
                .navigate('VirtualLook', { occasion, outfitId: currentOutfits[0].id })}
            />
          )}
          <Button variant="ghost" icon="construct-outline" label="Build my own" onPress={() => navigation.navigate('OutfitBuilder' as never)} />
        </View>
      </ScrollView>
    </ScreenWrapper>
  );
}

function SwipeCard({
  outfit,
  index,
  width,
  onSkip,
  onLike,
  onDislike,
  onSave,
  onWear,
}: {
  outfit: Outfit;
  index: number;
  width: number;
  onSkip: () => void;
  onLike: () => void;
  onDislike: () => void;
  onSave: () => void;
  onWear: () => void;
}) {
  const items = useWardrobeStore((s) => s.items);
  const outfitItems = items.filter((i) => outfit.itemIds.includes(i.id));
  const palette = useThemeColors();
  const translateX = useSharedValue(0);
  const translateY = useSharedValue(index * 8);

  const gesture = Gesture.Pan()
    .activeOffsetX([-12, 12])
    .failOffsetY([-14, 14])
    .onUpdate((e) => {
      translateX.value = e.translationX;
    })
    .onEnd((e) => {
      if (e.translationX > 120) runOnJS(onSave)();
      else if (e.translationX < -120) runOnJS(onSkip)();
      translateX.value = withSpring(0, { damping: 18, stiffness: 180 });
    });

  const style = useAnimatedStyle(() => ({
    transform: [
      { translateX: translateX.value },
      { translateY: translateY.value },
      { rotate: `${interpolate(translateX.value, [-200, 0, 200], [-8, 0, 8])}deg` },
      { scale: 1 - index * 0.05 },
    ],
    zIndex: 10 - index,
  }));
  const saveCue = useAnimatedStyle(() => ({
    opacity: interpolate(translateX.value, [20, 120], [0, 1], Extrapolation.CLAMP),
  }));
  const skipCue = useAnimatedStyle(() => ({
    opacity: interpolate(translateX.value, [-120, -20], [1, 0], Extrapolation.CLAMP),
  }));

  if (index > 0) return null;

  return (
    <GestureDetector gesture={gesture}>
      <Animated.View style={[style, { width }]} entering={FadeIn.duration(motion.long)}>
        <View className="bg-surface rounded-md border border-border overflow-hidden">
          <View className="relative" style={{ aspectRatio: 4 / 4.4 }}>
            <OutfitCollage outfit={outfit} />
            <GradientScrim color={landing.night} opacity={0.85} from={0.55} />
            <Animated.View style={saveCue} className="absolute top-4 left-4 flex-row items-center gap-1.5 px-3 py-1.5 rounded-full bg-stylist">
              <Ionicons name="bookmark" size={14} color={palette.stylistInk} />
              <Text className="font-body-semibold text-sm text-stylist-ink">Save</Text>
            </Animated.View>
            <Animated.View style={[skipCue, { backgroundColor: landing.inkPaper }]} className="absolute top-4 left-4 flex-row items-center gap-1.5 px-3 py-1.5 rounded-full">
              <Ionicons name="close" size={14} color={landing.ink} />
              <Text className="font-body-semibold text-sm" style={{ color: landing.ink }}>Skip</Text>
            </Animated.View>
            <View className="absolute left-5 right-5 bottom-5">
              <Text className="font-display text-3xl" style={{ color: landing.inkPaper }}>{outfit.name}</Text>
              {outfitItems.length > 0 && (
                <View className="flex-row gap-2 mt-3">
                  {outfitItems.map((item) => (
                    <AppImage
                      key={item.id}
                      source={{ uri: item.imageUrl }}
                      className="w-11 h-11 rounded-sm"
                      style={{ borderWidth: 1, borderColor: landing.nightRule }}
                      contentFit="cover"
                      accessibilityLabel={item.name}
                    />
                  ))}
                </View>
              )}
            </View>
          </View>
          <View className="p-5">
            <StylistNote text={outfit.explanation} />
            {index === 0 && outfit.comparisonExplanation && (
              <View className="mt-4 pt-4 border-t border-border">
                <Text className="text-text-primary font-body-semibold text-sm mb-1.5">Why it ranked first</Text>
                <Text className="text-text-secondary font-body text-sm">{outfit.comparisonExplanation}</Text>
                {outfit.comparisonAlternative && (
                  <Text className="text-text-tertiary font-body text-xs mt-2">Also compared: {outfit.comparisonAlternative}</Text>
                )}
                {outfit.confidenceNote && (
                  <Text className="text-text-tertiary font-body text-xs mt-2">{outfit.confidenceNote}</Text>
                )}
              </View>
            )}
          </View>
          <View className="flex-row border-t border-border">
            <CardAction icon="thumbs-down-outline" label="Not for me" onPress={onDislike} />
            <CardAction icon="heart-outline" label="Like" onPress={onLike} divider />
            <CardAction icon="bookmark-outline" label="Save" onPress={onSave} divider />
            <CardAction icon="checkmark-circle-outline" label="Wear today" onPress={onWear} divider accent />
          </View>
        </View>
      </Animated.View>
    </GestureDetector>
  );
}

function CardAction({
  icon,
  label,
  onPress,
  divider,
  accent,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  onPress: () => void;
  divider?: boolean;
  accent?: boolean;
}) {
  const palette = useThemeColors();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label === 'Not for me' ? 'Dislike outfit' : label === 'Like' ? 'Like outfit' : label === 'Save' ? 'Save outfit' : 'Wear today'}
      onPress={onPress}
      className={cn('flex-1 items-center justify-center py-3.5 gap-1 hover:bg-surface-raised', divider && 'border-l border-border')}
    >
      <Ionicons name={icon} size={22} color={accent ? palette.accent : palette.textPrimary} />
      <Text className={cn('font-body text-xs', accent ? 'text-accent font-body-medium' : 'text-text-secondary')}>{label}</Text>
    </Pressable>
  );
}
