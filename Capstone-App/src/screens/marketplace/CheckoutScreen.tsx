import { useState } from 'react';
import { useThemeColors } from '@/hooks/useThemeColors';
import { View, Text, ScrollView, Pressable } from 'react-native';
import Animated, { ZoomIn } from 'react-native-reanimated';
import { KeyboardAwareScroll } from '@/components/shared/KeyboardAwareScroll';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import { ScreenWrapper } from '@/components/shared/ScreenWrapper';
import { Header } from '@/components/shared/Header';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { useCartStore } from '@/store/cartStore';
import { marketplaceService } from '@/services';
import { formatCurrency } from '@/utils/helpers';
import { hapticLight } from '@/utils/haptics';

const PAYMENT_METHODS = [
  { id: 'card', label: 'Credit/Debit Card', icon: 'card-outline' as const },
  { id: 'upi', label: 'UPI', icon: 'phone-portrait-outline' as const },
  { id: 'wallet', label: 'Wallet', icon: 'wallet-outline' as const },
];

export function CheckoutScreen() {
  const navigation = useNavigation();
  const { items, total, clearCart } = useCartStore();
  const [payment, setPayment] = useState('card');
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [address, setAddress] = useState({ line1: '', city: 'New Delhi', pincode: '' });
  const palette = useThemeColors();

  const handlePlaceOrder = async () => {
    setLoading(true);
    await marketplaceService.placeOrder(items.map((item) => item.product.id));
    setLoading(false);
    clearCart();
    setSuccess(true);
  };

  if (success) {
    return (
      <ScreenWrapper className="items-center justify-center">
        <Animated.View entering={ZoomIn} className="items-center px-6 w-full self-center" style={{ maxWidth: 440 }}>
          <View className="w-20 h-20 rounded-full border border-border items-center justify-center mb-6">
            <Ionicons name="checkmark" size={34} color={palette.success} />
          </View>
          <Text className="text-text-primary font-display text-3xl mb-2">Order placed</Text>
          <Text className="text-text-secondary font-body text-center mb-8">
            Your order is confirmed. You’ll receive a confirmation email shortly.
          </Text>
          <Button label="Back to home" onPress={() => navigation.navigate('Main' as never)} />
        </Animated.View>
      </ScreenWrapper>
    );
  }

  return (
    <ScreenWrapper>
      <Header title="Checkout" showBack onBack={() => navigation.goBack()} />
      <KeyboardAwareScroll className="px-4">
        <Text className="text-text-primary font-display text-2xl mt-6 mb-4">Shipping address</Text>
        <Input label="Address Line" value={address.line1} onChangeText={(t) => setAddress((a) => ({ ...a, line1: t }))} />
        <Input label="City" value={address.city} onChangeText={(t) => setAddress((a) => ({ ...a, city: t }))} />
        <Input label="Pincode" value={address.pincode} onChangeText={(t) => setAddress((a) => ({ ...a, pincode: t }))} keyboardType="numeric" />

        <Text className="text-text-primary font-display text-2xl mb-4 mt-6">Payment method</Text>
        {PAYMENT_METHODS.map((m) => (
          <Pressable
            key={m.id}
            accessibilityRole="radio"
            accessibilityState={{ checked: payment === m.id }}
            accessibilityLabel={m.label}
            onPress={() => { hapticLight(); setPayment(m.id); }}
            className={`flex-row items-center px-4 min-h-14 rounded-sm border mb-2 ${payment === m.id ? 'border-primary bg-surface-raised' : 'border-border bg-surface'}`}
          >
            <Ionicons name={m.icon} size={22} color={payment === m.id ? palette.textPrimary : palette.textSecondary} />
            <Text className="text-text-primary font-body text-base ml-3 flex-1">{m.label}</Text>
            <View className={`w-5 h-5 rounded-full border items-center justify-center ${payment === m.id ? 'border-primary' : 'border-border-strong'}`}>
              {payment === m.id && <View className="w-2.5 h-2.5 rounded-full bg-primary" />}
            </View>
          </Pressable>
        ))}

        <View className="mt-6 pt-4 border-t border-text-primary mb-6 flex-row justify-between items-baseline">
          <Text className="text-text-secondary font-body">{items.length} {items.length === 1 ? 'item' : 'items'}, shipping included</Text>
          <Text className="text-text-primary font-display text-2xl tabular-nums">{formatCurrency(total() + 99)}</Text>
        </View>
      </KeyboardAwareScroll>

      <View className="px-4 pb-6 pt-3 border-t border-border">
        <Button size="lg" icon="lock-closed-outline" label="Place order" onPress={handlePlaceOrder} loading={loading} />
      </View>
    </ScreenWrapper>
  );
}
