import { View, Text, ScrollView } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { ScreenWrapper } from '@/components/shared/ScreenWrapper';
import { Header } from '@/components/shared/Header';
import { CartItemRow } from '@/components/marketplace/CartItem';
import { Button } from '@/components/ui/Button';
import { useCartStore } from '@/store/cartStore';
import { formatCurrency } from '@/utils/helpers';

export function CartScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<Record<string, object | undefined>>>();
  const { items, removeFromCart, total } = useCartStore();
  const subtotal = total();

  return (
    <ScreenWrapper empty={!items.length} emptyTitle="Your bag is empty" emptyMessage="Pieces you add from the marketplace will wait here." emptyActionLabel="Keep browsing" onEmptyAction={() => navigation.goBack()}>
      <Header title="Your bag" showBack onBack={() => navigation.goBack()} />
      <ScrollView className="flex-1 px-4">
        {items.map(({ product }) => (
          <CartItemRow key={product.id} product={product} onRemove={() => removeFromCart(product.id)} />
        ))}

        <View className="mt-8 pt-2 border-t border-text-primary">
          <View className="flex-row justify-between py-2">
            <Text className="text-text-secondary font-body">Subtotal</Text>
            <Text className="text-text-primary font-body tabular-nums">{formatCurrency(subtotal)}</Text>
          </View>
          <View className="flex-row justify-between py-2">
            <Text className="text-text-secondary font-body">Delivery</Text>
            <Text className="text-text-secondary font-body">Arranged by each seller</Text>
          </View>
          <View className="flex-row justify-between items-baseline pt-3 mt-1 border-t border-border">
            <Text className="text-text-primary font-body-semibold">Total</Text>
            <Text className="text-text-primary font-display text-2xl tabular-nums">{formatCurrency(subtotal)}</Text>
          </View>
        </View>
      </ScrollView>

      <View className="px-4 pb-6 pt-3 border-t border-border">
        <Button size="lg" icon="lock-closed-outline" label="Checkout" onPress={() => navigation.navigate('Checkout')} />
      </View>
    </ScreenWrapper>
  );
}
