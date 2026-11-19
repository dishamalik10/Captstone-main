import { useState, useRef } from 'react';
import { useThemeColors } from '@/hooks/useThemeColors';
import { View, Text, ScrollView, FlatList, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
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
import { useCartStore } from '@/store/cartStore';
import { useToastStore } from '@/components/ui/Toast';
import { formatCurrency } from '@/utils/helpers';


export function ProductDetailScreen() {
  const route = useRoute<RouteProp<{ params: { id: string } }>>();
  const navigation = useNavigation<NativeStackNavigationProp<Record<string, object | undefined>>>();
  const { data: product, isLoading, isError, refetch } = useProduct(route.params.id);
  const addToCart = useCartStore((s) => s.addToCart);
  const showToast = useToastStore((s) => s.show);
  const [imageIndex, setImageIndex] = useState(0);
  const { width } = useWindowDimensions();
  const palette = useThemeColors();

  if (isLoading) return <ScreenWrapper loading />;
  if (isError || !product) return <ScreenWrapper error="Product not found" onRetry={refetch} />;

  return (
    <ScreenWrapper>
      <Header showBack onBack={() => navigation.goBack()} />
      <ScrollView className="flex-1">
        <FlatList
          horizontal
          pagingEnabled
          data={product.imageUrls}
          keyExtractor={(_, i) => String(i)}
          onMomentumScrollEnd={(e) => setImageIndex(Math.round(e.nativeEvent.contentOffset.x / width))}
          renderItem={({ item }) => (
            <AppImage source={{ uri: item }} style={{ width, height: Math.min(width * 1.2, 560) }} contentFit="cover" />
          )}
        />
        {product.imageUrls.length > 1 && (
          <View className="flex-row justify-center gap-1.5 py-3" accessibilityLabel={`Image ${imageIndex + 1} of ${product.imageUrls.length}`}>
            {product.imageUrls.map((_, i) => (
              <View key={i} className={`h-0.5 rounded-full ${i === imageIndex ? 'w-6 bg-text-primary' : 'w-3 bg-border-strong'}`} />
            ))}
          </View>
        )}

        <View className="px-5 py-5 w-full self-center" style={{ maxWidth: 640 }}>
          <Badge label={product.condition.replace('_', ' ')} className="mb-3" />
          <Text accessibilityRole="header" className="text-text-primary font-display text-3xl">{product.title}</Text>
          <Text className="text-text-primary font-body-semibold text-2xl mt-2 tabular-nums">{formatCurrency(product.price)}</Text>
          <View className="flex-row items-center gap-1.5 mt-2">
            <Ionicons name="star" size={14} color={palette.accent} />
            <Text className="text-text-secondary font-body text-sm tabular-nums">
              {product.rating} from {product.reviewCount} reviews
            </Text>
          </View>
          <Text className="text-text-secondary font-body text-base mt-6 leading-6">{product.description}</Text>
          <View className="mt-8 pt-5 border-t border-border">
            <Text className="text-text-tertiary font-body text-sm mb-3">Sold by</Text>
            <SellerBadge seller={product.seller} />
          </View>
        </View>
      </ScrollView>

      <View className="px-4 pb-6 gap-3 border-t border-border pt-4 flex-row">
        <Button
          className="flex-1"
          icon="bag-add-outline"
          label="Add to cart"
          onPress={() => {
            addToCart(product);
            showToast('Added to cart', 'success');
          }}
        />
        <Button className="flex-1" variant="secondary" label="Message seller" onPress={() => showToast('Message sent', 'info')} />
      </View>
    </ScreenWrapper>
  );
}
