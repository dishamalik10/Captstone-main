import { useState } from 'react';
import { View, Text, ScrollView, RefreshControl, Pressable } from 'react-native';
import Animated, { FadeIn, FadeInDown } from 'react-native-reanimated';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { ScreenWrapper } from '@/components/shared/ScreenWrapper';
import { AppImage } from '@/components/shared/AppImage';
import { OutfitCollage } from '@/components/outfits/OutfitCollage';
import { GradientScrim } from '@/components/shared/GradientScrim';
import { Wordmark } from '@/components/shared/Wordmark';
import { Card } from '@/components/ui/Card';
import { Chip } from '@/components/ui/Chip';
import { Button } from '@/components/ui/Button';
import { Skeleton } from '@/components/ui/Skeleton';
import { OutfitCard } from '@/components/outfits/OutfitCard';
import { OCCASIONS } from '@/constants/categories';
import { useOutfitRecommendations, useWeather, useWardrobeStats, useSocialFeed } from '@/hooks';
import { useAuthStore } from '@/store/authStore';
import { useCartStore } from '@/store/cartStore';
import { getGreeting, formatDate } from '@/utils/helpers';
import { hapticLight } from '@/utils/haptics';
import { useThemeColors } from '@/hooks/useThemeColors';
import { landing, motion } from '@/constants/theme';
import type { Occasion } from '@/types';

export function HomeScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<Record<string, object | undefined>>>();
  const palette = useThemeColors();
  const user = useAuthStore((s) => s.user);
  const cartCount = useCartStore((s) => s.itemCount());
  const { data: weather, isLoading: weatherLoading, refetch: refetchWeather, isError: weatherError } = useWeather();
  const { data: stats, isLoading: statsLoading, refetch: refetchStats } = useWardrobeStats();
  const { data: feed, isLoading: feedLoading, refetch: refetchFeed } = useSocialFeed();
  const [selectedOccasion, setSelectedOccasion] = useState<Occasion>('casual');
  const {
    data: recommendations,
    refetch: refetchRecommendations,
    isFetching: recommendationsLoading,
  } = useOutfitRecommendations(selectedOccasion);

  const loading = weatherLoading || statsLoading || feedLoading || recommendationsLoading;
  const todayOutfit = recommendations?.[0];
  const firstName = user?.fullName?.split(' ')[0] ?? 'there';
  const occasionLabel = OCCASIONS.find((o) => o.key === selectedOccasion)?.label ?? selectedOccasion;

  return (
    <ScreenWrapper>
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ paddingBottom: 120, width: '100%', maxWidth: 760, alignSelf: 'center' }}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={loading}
            onRefresh={() => {
              refetchWeather();
              refetchStats();
              refetchFeed();
              refetchRecommendations();
            }}
            tintColor={palette.accent}
          />
        }
      >
        {/* Greeting */}
        <View className="px-5 pt-3 pb-6">
          <View className="flex-row items-center justify-between h-11">
            <Wordmark size={15} color={palette.textPrimary} style={{ paddingLeft: 0 }} />
            {cartCount > 0 && (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={`Cart, ${cartCount} items`}
                onPress={() => navigation.navigate('Cart')}
                className="w-11 h-11 items-center justify-center rounded-full border border-border"
              >
                <Ionicons name="bag-outline" size={19} color={palette.textPrimary} />
                <View className="absolute top-1.5 right-1.5 min-w-4 h-4 px-1 rounded-full bg-primary items-center justify-center">
                  <Text className="text-primary-ink font-body-semibold text-[10px]">{cartCount}</Text>
                </View>
              </Pressable>
            )}
          </View>
          <Animated.Text
            entering={FadeInDown.duration(motion.long)}
            accessibilityRole="header"
            className="text-text-primary font-display text-4xl tracking-tight mt-6"
          >
            {getGreeting()},{'\n'}
            {firstName}.
          </Animated.Text>
          <Animated.View entering={FadeInDown.duration(motion.long).delay(60)} className="flex-row flex-wrap items-center gap-2 mt-4">
            <Text className="text-text-secondary font-body text-base">{formatDate(new Date())}</Text>
            {weather && (
              <View className="flex-row items-center gap-1.5 px-3 h-8 rounded-full border border-border">
                <Ionicons name="partly-sunny-outline" size={15} color={palette.accent} />
                <Text className="text-text-primary font-body-medium text-sm tabular-nums">
                  {weather.temperature}°C
                </Text>
                <Text className="text-text-secondary font-body text-sm">
                  {weather.condition} in {weather.location}
                </Text>
              </View>
            )}
          </Animated.View>
          {weatherError && (
            <Text className="text-text-tertiary font-body text-sm mt-3">
              Add a valid city in your profile to style for live weather.
            </Text>
          )}
        </View>

        {/* Today's look */}
        <View className="px-5 mb-10">
          <View className="mb-4">
            <Text accessibilityRole="header" className="text-text-primary font-display text-2xl">
              Today’s look
            </Text>
          </View>
          {recommendationsLoading && !todayOutfit ? (
            <Skeleton className="h-[440px] w-full rounded-md" />
          ) : todayOutfit ? (
            <Animated.View entering={FadeIn.duration(motion.long)}>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={`Today's recommended outfit: ${todayOutfit.name}`}
                onPress={() => hapticLight()}
                className="rounded-md overflow-hidden h-[440px] border border-border"
              >
                <OutfitCollage outfit={todayOutfit} />
                <GradientScrim color={landing.night} opacity={0.88} from={0.55} />
                <View className="absolute left-0 right-0 bottom-0 p-6">
                  <View className="self-start rounded-full px-3 py-1 mb-3 bg-stylist">
                    <Text className="font-body-semibold text-xs text-stylist-ink">{occasionLabel}</Text>
                  </View>
                  <Text className="font-display text-3xl" style={{ color: landing.inkPaper }}>
                    {todayOutfit.name}
                  </Text>
                  <Text className="font-body text-base mt-2" numberOfLines={3} style={{ color: landing.nightMuted }}>
                    {todayOutfit.explanation}
                  </Text>
                </View>
              </Pressable>
            </Animated.View>
          ) : (
            <Card className="p-6 items-start">
              <View className="w-12 h-12 rounded-full bg-surface-raised border border-border items-center justify-center mb-4">
                <Ionicons name="shirt-outline" size={22} color={palette.textPrimary} />
              </View>
              <Text className="text-text-primary font-display text-xl">Build your wardrobe first</Text>
              <Text className="text-text-secondary font-body text-base mt-2 mb-5">
                Upload a dress, or a top and a bottom, and AURA will put together today’s look.
              </Text>
              <Button label="Add pieces" icon="add" size="sm" onPress={() => navigation.navigate('Wardrobe')} />
            </Card>
          )}
        </View>

        {/* Occasion */}
        <Text accessibilityRole="header" className="text-text-primary font-display text-2xl px-5 mb-1">
          Dress for the moment
        </Text>
        <Text className="text-text-secondary font-body text-sm px-5 mb-3">Choose where you’re going.</Text>
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={{ flexGrow: 0 }}
          contentContainerStyle={{ paddingHorizontal: 20 }}
          className="mb-10"
        >
          {OCCASIONS.map((o) => (
            <Chip
              key={o.key}
              label={o.label}
              icon={o.icon as keyof typeof Ionicons.glyphMap}
              selected={selectedOccasion === o.key}
              onPress={() => setSelectedOccasion(o.key)}
            />
          ))}
        </ScrollView>

        {/* Quick actions */}
        <View className="flex-row px-5 gap-3 mb-10">
          <QuickAction
            icon="chatbubble-ellipses-outline"
            title="Ask your stylist"
            line="Plans, colours, pairings"
            onPress={() => navigation.navigate('Chat')}
          />
          <QuickAction
            icon="analytics-outline"
            title="Analyse wardrobe"
            line="Gaps and strengths"
            onPress={() => navigation.navigate('StyleAnalysis')}
          />
        </View>

        {/* Snapshot */}
        <Text accessibilityRole="header" className="text-text-primary font-display text-2xl px-5 mb-4">
          Wardrobe at a glance
        </Text>
        <View className="mx-5 mb-10 flex-row border-y border-border">
          {stats ? (
            <>
              <Figure value={String(stats.totalItems)} label="Pieces" large />
              <Figure value={stats.mostWorn.name} label={`Most worn, ${stats.mostWorn.count}×`} divider />
              <Figure value={stats.leastWorn.name} label="Least worn" divider />
            </>
          ) : (
            <View className="flex-1 flex-row py-5 gap-4">
              <Skeleton className="h-10 flex-1" />
              <Skeleton className="h-10 flex-1" />
              <Skeleton className="h-10 flex-1" />
            </View>
          )}
        </View>

        {/* Trending */}
        {(feed?.length ?? 0) > 0 && (
          <>
            <View className="flex-row items-end justify-between px-5 mb-4">
              <Text accessibilityRole="header" className="text-text-primary font-display text-2xl">
                From the community
              </Text>
              <Pressable
                accessibilityRole="link"
                accessibilityLabel="View social feed"
                hitSlop={10}
                onPress={() => navigation.navigate('SocialFeed')}
              >
                <Text className="text-text-primary font-body-medium text-sm underline">See all</Text>
              </Pressable>
            </View>
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              style={{ flexGrow: 0 }}
              contentContainerStyle={{ paddingHorizontal: 20, gap: 12 }}
              className="mb-8"
            >
              {(feed ?? []).slice(0, 3).map((post) => (
                <View key={post.id} className="w-60">
                  <OutfitCard
                    outfit={{
                      id: post.id,
                      name: post.caption,
                      occasion: 'casual',
                      compatibilityScore: 90,
                      imageUrl: post.outfitImageUrl,
                      itemIds: [],
                      explanation: post.caption,
                    }}
                    compact
                  />
                </View>
              ))}
            </ScrollView>
          </>
        )}

        {cartCount > 0 && (
          <View className="px-5 mb-8">
            <Card pressable onPress={() => navigation.navigate('Cart')} className="flex-row items-center justify-between">
              <View>
                <Text className="text-text-primary font-body-semibold">Continue shopping</Text>
                <Text className="text-text-secondary font-body text-sm">
                  {cartCount} {cartCount === 1 ? 'item' : 'items'} in your cart
                </Text>
              </View>
              <Ionicons name="arrow-forward" size={20} color={palette.textPrimary} />
            </Card>
          </View>
        )}
      </ScrollView>
    </ScreenWrapper>
  );
}

function QuickAction({
  icon,
  title,
  line,
  onPress,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  line: string;
  onPress: () => void;
}) {
  const palette = useThemeColors();
  return (
    <Card pressable onPress={onPress} accessibilityLabel={title} className="flex-1 p-4">
      <View className="w-10 h-10 rounded-full border border-border bg-background items-center justify-center">
        <Ionicons name={icon} size={18} color={palette.textPrimary} />
      </View>
      <Text className="text-text-primary font-display text-xl mt-4">{title}</Text>
      <Text className="text-text-secondary font-body text-sm mt-0.5">{line}</Text>
    </Card>
  );
}

function Figure({ value, label, large, divider }: { value: string; label: string; large?: boolean; divider?: boolean }) {
  return (
    <View className={`flex-1 py-5 ${divider ? 'pl-4 border-l border-border' : 'pr-4'}`}>
      <Text
        numberOfLines={1}
        className={large ? 'text-text-primary font-display text-3xl tabular-nums' : 'text-text-primary font-body-medium text-base mt-2'}
      >
        {value}
      </Text>
      <Text className="text-text-secondary font-body text-xs mt-1">{label}</Text>
    </View>
  );
}
