import { Alert, ScrollView, Text, View } from 'react-native';
import { useState } from 'react';
import { useNavigation } from '@react-navigation/native';
import * as ImagePicker from 'expo-image-picker';
import { Ionicons } from '@expo/vector-icons';
import { ScreenWrapper } from '@/components/shared/ScreenWrapper';
import { Header } from '@/components/shared/Header';
import { Button } from '@/components/ui/Button';
import { useStyleAnalysis } from '@/hooks';
import { wardrobeService } from '@/services';
import type { PurchaseImpact } from '@/types';
import { useThemeColors } from '@/hooks/useThemeColors';
import { layout } from '@/constants/theme';

const COLOR_SWATCH: Record<string, string> = {
  black: '#171717', white: '#F5F5F0', grey: '#808080', gray: '#808080', red: '#B83A3A', blue: '#3B68A0',
  green: '#4F7651', yellow: '#D6B84B', brown: '#795548', beige: '#D8C3A5', pink: '#D98CA3', purple: '#76518A',
  orange: '#D8783C', navy: '#1F2D4D', gold: '#C8A96E',
};

export function StyleAnalysisScreen() {
  const navigation = useNavigation();
  const { data, isLoading, isError, refetch } = useStyleAnalysis();
  const [purchase, setPurchase] = useState<PurchaseImpact | null>(null);
  const [checkingPurchase, setCheckingPurchase] = useState(false);
  const palette = useThemeColors();

  const testPurchase = async () => {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      quality: 0.9,
    });
    if (result.canceled || !result.assets[0]) return;
    setCheckingPurchase(true);
    setPurchase(null);
    try {
      setPurchase(await wardrobeService.analyzePurchase(result.assets[0]));
    } catch (error) {
      Alert.alert('Could not analyze item', error instanceof Error ? error.message : 'Please try another image.');
    } finally {
      setCheckingPurchase(false);
    }
  };

  if (isLoading) return <ScreenWrapper loading />;
  if (isError || !data) {
    return <ScreenWrapper error="Could not analyze your wardrobe." onRetry={refetch} />;
  }

  const categories = Object.entries(data.categoryCounts).sort((a, b) => b[1] - a[1]);
  const maxCategory = Math.max(1, ...categories.map(([, n]) => n));
  const colours = [...data.dominantColors].sort((a, b) => b.count - a.count);
  const maxColour = Math.max(1, ...colours.map((c) => c.count));
  const coverage = Math.max(0, Math.min(100, data.wardrobeCoverage));

  return (
    <ScreenWrapper>
      <Header title="Style analysis" subtitle="Gaps and strengths in your wardrobe" showBack onBack={() => navigation.goBack()} />
      <ScrollView contentContainerStyle={{ padding: 20, paddingBottom: 100 }}>
        <View className="w-full self-center" style={{ maxWidth: layout.reading }}>
          {/* Headline figure */}
          <View className="pb-6 mb-8 border-b border-border">
            <Text className="text-text-secondary font-body text-sm">Wardrobe coverage</Text>
            <Text className="text-text-primary font-display tabular-nums" style={{ fontSize: 64, lineHeight: 70 }}>
              {coverage}%
            </Text>
            <View
              className="h-1.5 rounded-full bg-surface-raised overflow-hidden mt-2"
              accessibilityRole="progressbar"
              accessibilityValue={{ min: 0, max: 100, now: coverage }}
            >
              <View className="h-full rounded-full bg-accent" style={{ width: `${coverage}%` }} />
            </View>
            <Text className="text-text-secondary font-body text-sm mt-3 tabular-nums">
              Based on {data.totalItems} uploaded {data.totalItems === 1 ? 'piece' : 'pieces'}
            </Text>
          </View>

          {/* Category counts: one series, magnitude, sorted, direct-labelled */}
          <Text accessibilityRole="header" className="text-text-primary font-display text-2xl mb-1">Pieces by category</Text>
          <Text className="text-text-secondary font-body text-sm mb-5">How your wardrobe is spread today.</Text>
          <View className="gap-3 mb-10">
            {categories.map(([category, count]) => (
              <View key={category} accessibilityLabel={`${category}: ${count}`} className="flex-row items-center gap-3">
                <Text className="text-text-primary font-body text-sm capitalize w-24" numberOfLines={1}>{category}</Text>
                <View className="flex-1 h-5 justify-center">
                  <View className="h-3.5 rounded-r bg-accent" style={{ width: `${Math.max(3, (count / maxCategory) * 100)}%` }} />
                </View>
                <Text className="text-text-secondary font-body-medium text-sm w-6 text-right tabular-nums">{count}</Text>
              </View>
            ))}
          </View>

          {/* Dominant colours: identity is the garment colour itself, so the swatch carries it */}
          <Text accessibilityRole="header" className="text-text-primary font-display text-2xl mb-1">Dominant colours</Text>
          <Text className="text-text-secondary font-body text-sm mb-5">The shades you reach for most.</Text>
          <View className="gap-3 mb-10">
            {colours.map((color) => (
              <View key={color.name} accessibilityLabel={`${color.name}: ${color.count}`} className="flex-row items-center gap-3">
                <View
                  className="w-4 h-4 rounded-full border border-border-strong"
                  style={{ backgroundColor: COLOR_SWATCH[color.name.toLowerCase()] ?? palette.surfaceRaised }}
                />
                <Text className="text-text-primary font-body text-sm capitalize w-20" numberOfLines={1}>{color.name}</Text>
                <View className="flex-1 h-5 justify-center">
                  <View className="h-3.5 rounded-r bg-text-tertiary" style={{ width: `${Math.max(3, (color.count / maxColour) * 100)}%` }} />
                </View>
                <Text className="text-text-secondary font-body-medium text-sm w-6 text-right tabular-nums">{color.count}</Text>
              </View>
            ))}
          </View>

          {/* Purchase check */}
          <View className="rounded-md border border-border bg-surface p-5 mb-6">
            <View className="flex-row items-start gap-4 mb-5">
              <View className="w-11 h-11 rounded-full border border-border bg-background items-center justify-center">
                <Ionicons name="bag-check-outline" size={20} color={palette.textPrimary} />
              </View>
              <View className="flex-1">
                <Text className="text-text-primary font-display text-xl">Thinking of buying something?</Text>
                <Text className="text-text-secondary font-body text-sm mt-1">See how a new piece would fit what you already own.</Text>
              </View>
            </View>
            <Button label="Check a potential purchase" icon="image-outline" onPress={testPurchase} loading={checkingPurchase} />
            <Text className="text-text-tertiary font-body text-xs mt-3">
              The photo is analysed temporarily and is not added to your wardrobe.
            </Text>
          </View>

          {purchase && (
            <View className="rounded-md border border-text-primary bg-surface p-5 mb-10">
              <View className="flex-row justify-between items-start gap-4">
                <View className="flex-1">
                  <Text className="text-text-secondary font-body text-sm">Purchase impact</Text>
                  <Text className="text-text-primary font-display text-2xl mt-1">{purchase.headline}</Text>
                  <Text className="text-text-secondary font-body capitalize mt-2">
                    {purchase.detectedItem.color} {purchase.detectedItem.productType}
                  </Text>
                </View>
                <View className="items-end">
                  <Text className="text-text-primary font-display text-4xl tabular-nums">{purchase.purchaseScore}</Text>
                  <Text className="text-text-tertiary font-body text-xs">out of 100</Text>
                </View>
              </View>
              <View className="flex-row mt-5 border-y border-border">
                <View className="flex-1 py-3 pr-3">
                  <Text className="text-text-tertiary font-body text-xs">Verdict</Text>
                  <Text className="text-text-primary font-body-semibold text-base capitalize mt-0.5">{purchase.verdict}</Text>
                </View>
                <View className="flex-1 py-3 pl-3 border-l border-border">
                  <Text className="text-text-tertiary font-body text-xs">New outfits possible</Text>
                  <Text className="text-text-primary font-body-semibold text-base mt-0.5 tabular-nums">{purchase.newOutfits}</Text>
                </View>
              </View>
              <Text className="text-text-primary font-body-semibold mt-5 mb-2">Why this score</Text>
              {purchase.reasons.map((reason) => (
                <View key={reason} className="flex-row mb-2">
                  <Ionicons name="checkmark" size={16} color={palette.accent} style={{ marginTop: 3, marginRight: 8 }} />
                  <Text className="text-text-secondary font-body flex-1">{reason}</Text>
                </View>
              ))}
              {!!purchase.similarItems.length && (
                <View className="flex-row items-center gap-2 mt-2">
                  <Ionicons name="alert-circle-outline" size={16} color={palette.warning} />
                  <Text className="text-warning font-body flex-1">
                    You already own {purchase.similarItems.length} similar item{purchase.similarItems.length === 1 ? '' : 's'}.
                  </Text>
                </View>
              )}
              <Text className="text-text-tertiary font-body text-xs mt-4">{purchase.disclaimer}</Text>
            </View>
          )}

          {/* Recommendations */}
          <Text accessibilityRole="header" className="text-text-primary font-display text-2xl mb-4">Worth considering</Text>
          <View className="border-t border-text-primary">
            {data.recommendations.map((item) => (
              <View key={`${item.category}-${item.title}`} className="py-4 border-b border-border">
                <View className="flex-row justify-between items-center gap-3">
                  <Text className="text-text-primary font-body-semibold text-base flex-1">{item.title}</Text>
                  <View className="flex-row items-center gap-1.5">
                    <Ionicons
                      name={item.priority === 'high' ? 'arrow-up-circle-outline' : 'ellipse-outline'}
                      size={14}
                      color={item.priority === 'high' ? palette.warning : palette.textTertiary}
                    />
                    <Text className="text-text-secondary font-body text-xs capitalize">{item.priority} priority</Text>
                  </View>
                </View>
                <Text className="text-text-secondary font-body mt-1.5">{item.reason}</Text>
                <Text className="text-text-tertiary font-body text-xs mt-2 tabular-nums">
                  You own {item.owned}. A useful baseline is {item.suggestedMinimum}.
                </Text>
              </View>
            ))}
            {!data.recommendations.length && (
              <Text className="text-text-secondary font-body py-4">Your wardrobe has balanced category coverage.</Text>
            )}
          </View>
          <Text className="text-text-tertiary font-body text-sm mt-6">{data.disclaimer}</Text>
        </View>
      </ScrollView>
    </ScreenWrapper>
  );
}
