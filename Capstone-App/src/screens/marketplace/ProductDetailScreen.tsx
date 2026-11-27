import { useState } from 'react';
import { View, Text, ScrollView, FlatList, useWindowDimensions } from 'react-native';
import { useRoute, useNavigation } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { ScreenWrapper } from '@/components/shared/ScreenWrapper';
import { Header } from '@/components/shared/Header';
import { AppImage } from '@/components/shared/AppImage';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { SellerBadge } from '@/components/marketplace/SellerBadge';
import { useProduct } from '@/hooks';
import { fitService, marketplaceService } from '@/services';
import { FitAdviceCard } from '@/components/fit/FitAdviceCard';
import { useAuthStore } from '@/store/authStore';
import { ReportButton, ReportSheet } from '@/components/shared/ReportSheet';
import { useCartStore } from '@/store/cartStore';
import { useToastStore } from '@/components/ui/Toast';
import { formatCurrency } from '@/utils/helpers';
import { layout } from '@/constants/theme';

const CONDITION_LABEL = { new: 'New with tags', like_new: 'Like new', good: 'Good', fair: 'Fair' } as const;

export function ProductDetailScreen() {
  const route = useRoute<RouteProp<{ params: { id: string } }>>();
  const navigation = useNavigation<NativeStackNavigationProp<Record<string, object | undefined>>>();
  const { data: product, isLoading, isError, refetch } = useProduct(route.params.id);
  const myId = useAuthStore((s) => s.user?.id);
  const addToCart = useCartStore((s) => s.addToCart);
  const inBag = useCartStore((s) => s.items.some((i) => i.product.id === route.params.id));
  const showToast = useToastStore((s) => s.show);
  const [imageIndex, setImageIndex] = useState(0);
  const [opening, setOpening] = useState(false);
  const [reporting, setReporting] = useState(false);
  const { width } = useWindowDimensions();
  const imageWidth = Math.min(width, layout.reading);

  if (isLoading) return <ScreenWrapper loading />;
  if (isError || !product) return <ScreenWrapper error="Listing not found" onRetry={refetch} />;

  const mine = product.seller.id === myId;
  const available = product.status === 'active';

  const messageSeller = async () => {
    setOpening(true);
    try {
      const conversation = await marketplaceService.startConversation(product.id);
      navigation.navigate('Conversation', { id: conversation.id });
    } catch {
      showToast('Could not open the chat', 'error');
    } finally {
      setOpening(false);
    }
  };

  const details: [string, string][] = [
    ['Condition', CONDITION_LABEL[product.condition]],
    ['Size', product.size],
    ['Brand', product.brand],
    ['Category', product.category],
  ].filter((entry): entry is [string, string] => Boolean(entry[1]));

  return (
    <ScreenWrapper>
      <Header showBack onBack={() => navigation.goBack()} rightAction={mine ? undefined : <ReportButton onPress={() => setReporting(true)} />} />
      <ReportSheet
        visible={reporting}
        onClose={() => setReporting(false)}
        target={{ type: 'listing', id: product.id, label: 'this listing' }}
        user={{ id: product.seller.id, name: product.seller.name }}
        onBlocked={() => navigation.goBack()}
      />
      <ScrollView className="flex-1" contentContainerStyle={{ paddingBottom: 24 }}>
        <View className="self-center" style={{ width: imageWidth }}>
          <FlatList
            horizontal
            pagingEnabled
            data={product.imageUrls}
            keyExtractor={(_, i) => String(i)}
            showsHorizontalScrollIndicator={false}
            onMomentumScrollEnd={(e) => setImageIndex(Math.round(e.nativeEvent.contentOffset.x / imageWidth))}
            renderItem={({ item }) => (
              <AppImage source={{ uri: item }} style={{ width: imageWidth, height: Math.min(imageWidth * 1.2, 600) }} contentFit="cover" />
            )}
          />
        </View>
        {product.imageUrls.length > 1 && (
          <View className="flex-row justify-center gap-1.5 py-3" accessibilityLabel={`Photo ${imageIndex + 1} of ${product.imageUrls.length}`}>
            {product.imageUrls.map((_, i) => (
              <View key={i} className={`h-0.5 rounded-full ${i === imageIndex ? 'w-6 bg-text-primary' : 'w-3 bg-border-strong'}`} />
            ))}
          </View>
        )}

        <View className="px-5 py-5 w-full self-center" style={{ maxWidth: layout.reading }}>
          <View className="flex-row gap-2 mb-3">
            {!available && <Badge label={product.status === 'sold' ? 'Sold' : 'Paused'} />}
            {mine && <Badge label="Your listing" variant="accent" />}
          </View>
          <Text accessibilityRole="header" className="text-text-primary font-display text-3xl">{product.title}</Text>
          <Text className="text-text-primary font-body-semibold text-2xl mt-2 tabular-nums">{formatCurrency(product.price)}</Text>

          <View className="mt-6 border-t border-text-primary">
            {details.map(([label, value]) => (
              <View key={label} className="flex-row justify-between py-3 border-b border-border">
                <Text className="text-text-secondary font-body text-sm">{label}</Text>
                <Text className="text-text-primary font-body-medium text-base capitalize">{value}</Text>
              </View>
            ))}
          </View>

          {!!product.description && (
            <Text className="text-text-secondary font-body text-base mt-6 leading-6">{product.description}</Text>
          )}
          {!mine && myId && !['shoes', 'accessories'].includes(product.category) && (
            <FitAdviceCard queryKey={['listing', product.id, product.size]} load={() => fitService.forListing(product.id)} title="Will it fit you?" />
          )}
          <View className="mt-8 pt-5 border-t border-border">
            <Text className="text-text-tertiary font-body text-sm mb-3">Sold by</Text>
            <SellerBadge seller={product.seller} />
          </View>
        </View>
      </ScrollView>

      <View className="px-4 pb-6 pt-4 border-t border-border">
        <View className="w-full self-center gap-3" style={{ maxWidth: layout.reading }}>
          {mine ? (
            <Button icon="storefront-outline" label="Manage in seller dashboard" onPress={() => navigation.navigate('SellerDashboard')} />
          ) : (
            <>
              {available && (
                <View className="flex-row gap-3">
                  <Button
                    className="flex-1"
                    icon="flash-outline"
                    label="Buy now"
                    onPress={() => {
                      addToCart(product);
                      navigation.navigate('Checkout');
                    }}
                  />
                  <Button
                    className="flex-1"
                    variant="secondary"
                    icon={inBag ? 'checkmark' : 'bag-add-outline'}
                    label={inBag ? 'In your bag' : 'Add to bag'}
                    onPress={() => {
                      if (inBag) return navigation.navigate('Cart');
                      addToCart(product);
                      showToast('Added to your bag', 'success');
                    }}
                  />
                </View>
              )}
              <Button
                variant={available ? 'ghost' : 'secondary'}
                icon="chatbubble-ellipses-outline"
                label={available ? 'Message seller' : 'Sold · Message seller'}
                loading={opening}
                onPress={() => void messageSeller()}
              />
            </>
          )}
        </View>
      </View>
    </ScreenWrapper>
  );
}
