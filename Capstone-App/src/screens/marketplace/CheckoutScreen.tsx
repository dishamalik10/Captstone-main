import { useState } from 'react';
import { View, Text, Pressable } from 'react-native';
import Animated, { ZoomIn } from 'react-native-reanimated';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { KeyboardAwareScroll } from '@/components/shared/KeyboardAwareScroll';
import { ScreenWrapper } from '@/components/shared/ScreenWrapper';
import { Header } from '@/components/shared/Header';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { useToastStore } from '@/components/ui/Toast';
import { useRefreshMarketplace } from '@/hooks';
import { useThemeColors } from '@/hooks/useThemeColors';
import { marketplaceService } from '@/services';
import { useAuthStore } from '@/store/authStore';
import { useCartStore } from '@/store/cartStore';
import type { PaymentMethod, ShippingAddress } from '@/types';
import { cn, formatCurrency } from '@/utils/helpers';
import { hapticLight } from '@/utils/haptics';
import { layout } from '@/constants/theme';

const PAYMENT_METHODS: { id: PaymentMethod; label: string; hint: string; icon: keyof typeof Ionicons.glyphMap }[] = [
  { id: 'cod', label: 'Cash on delivery', hint: 'Pay the seller when the item arrives', icon: 'cash-outline' },
  { id: 'upi', label: 'UPI to the seller', hint: 'The seller shares their UPI ID in chat', icon: 'phone-portrait-outline' },
];

type Errors = Partial<Record<keyof ShippingAddress, string>>;

function validate(address: ShippingAddress): Errors {
  const errors: Errors = {};
  if (!address.name.trim()) errors.name = 'Enter the recipient’s name';
  if (!/^[6-9]\d{9}$/.test(address.phone.replace(/\D/g, '').slice(-10))) errors.phone = 'Enter a 10-digit mobile number';
  if (address.line1.trim().length < 5) errors.line1 = 'Enter the house number and street';
  if (!address.city.trim()) errors.city = 'Enter the city';
  if (!/^\d{6}$/.test(address.pincode.trim())) errors.pincode = 'Enter a 6-digit pincode';
  return errors;
}

export function CheckoutScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<Record<string, object | undefined>>>();
  const user = useAuthStore((s) => s.user);
  const { items, total, clearCart } = useCartStore();
  const refreshMarketplace = useRefreshMarketplace();
  const showToast = useToastStore((s) => s.show);
  const [payment, setPayment] = useState<PaymentMethod>('cod');
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [errors, setErrors] = useState<Errors>({});
  const [address, setAddress] = useState<ShippingAddress>({
    name: user?.fullName ?? '', phone: '', line1: '', city: user?.location ?? '', pincode: '',
  });
  const palette = useThemeColors();
  const sellers = new Set(items.map((item) => item.product.seller.id)).size;

  const field = (key: keyof ShippingAddress) => ({
    value: address[key],
    error: errors[key],
    onChangeText: (text: string) => {
      setAddress((current) => ({ ...current, [key]: text }));
      if (errors[key]) setErrors((current) => ({ ...current, [key]: undefined }));
    },
  });

  const handlePlaceOrder = async () => {
    const found = validate(address);
    setErrors(found);
    if (Object.keys(found).length) return;
    setLoading(true);
    try {
      await marketplaceService.placeOrder(items.map((item) => item.product.id), address, payment);
      clearCart();
      refreshMarketplace();
      setSuccess(true);
    } catch (error) {
      const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      showToast(typeof detail === 'string' ? detail : 'Could not place the order', 'error');
      refreshMarketplace();
    } finally {
      setLoading(false);
    }
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
            {sellers > 1 ? 'The sellers have' : 'The seller has'} been notified. Track it in My orders, and message the seller there about delivery{payment === 'upi' ? ' and their UPI ID' : ''}.
          </Text>
          <View className="w-full gap-3">
            <Button label="View my orders" onPress={() => navigation.replace('MyOrders')} />
            <Button variant="ghost" label="Keep shopping" onPress={() => navigation.navigate('Marketplace')} />
          </View>
        </Animated.View>
      </ScreenWrapper>
    );
  }

  return (
    <ScreenWrapper empty={!items.length} emptyTitle="Your bag is empty" emptyMessage="Add a piece from the marketplace first." emptyActionLabel="Browse" onEmptyAction={() => navigation.navigate('Marketplace')}>
      <Header title="Checkout" showBack onBack={() => navigation.goBack()} />
      <KeyboardAwareScroll className="px-4">
        <View className="w-full self-center" style={{ maxWidth: layout.reading }}>
          <Text className="text-text-primary font-display text-2xl mt-6 mb-4">Deliver to</Text>
          <Input label="Full name" autoComplete="name" {...field('name')} />
          <Input label="Mobile number" keyboardType="phone-pad" autoComplete="tel" {...field('phone')} />
          <Input label="House number and street" autoComplete="street-address" {...field('line1')} />
          <View className="flex-row gap-3">
            <Input label="City" containerClassName="flex-1" {...field('city')} />
            <Input label="Pincode" keyboardType="number-pad" maxLength={6} containerClassName="flex-1" {...field('pincode')} />
          </View>

          <Text className="text-text-primary font-display text-2xl mb-4 mt-4">Payment</Text>
          {PAYMENT_METHODS.map((m) => (
            <Pressable
              key={m.id}
              accessibilityRole="radio"
              accessibilityState={{ checked: payment === m.id }}
              accessibilityLabel={`${m.label}. ${m.hint}`}
              onPress={() => { hapticLight(); setPayment(m.id); }}
              className={cn('flex-row items-center px-4 py-3 rounded-sm border mb-2', payment === m.id ? 'border-primary bg-surface-raised' : 'border-border bg-surface')}
            >
              <Ionicons name={m.icon} size={22} color={payment === m.id ? palette.textPrimary : palette.textSecondary} />
              <View className="ml-3 flex-1">
                <Text className="text-text-primary font-body text-base">{m.label}</Text>
                <Text className="text-text-secondary font-body text-xs">{m.hint}</Text>
              </View>
              <View className={cn('w-5 h-5 rounded-full border items-center justify-center', payment === m.id ? 'border-primary' : 'border-border-strong')}>
                {payment === m.id && <View className="w-2.5 h-2.5 rounded-full bg-primary" />}
              </View>
            </Pressable>
          ))}
          <Text className="text-text-tertiary font-body text-xs mt-1">
            AURA doesn’t take payment. You pay the seller directly, so only pay once you’ve agreed the details in chat.
            Each item is held for you for 72 hours; if the seller hasn’t shipped it by then, the order is cancelled and the item goes back on sale.
          </Text>

          <View className="mt-6 pt-4 border-t border-text-primary mb-6 flex-row justify-between items-baseline">
            <Text className="text-text-secondary font-body">
              {items.length} {items.length === 1 ? 'item' : 'items'}{sellers > 1 ? ` from ${sellers} sellers` : ''}
            </Text>
            <Text className="text-text-primary font-display text-2xl tabular-nums">{formatCurrency(total())}</Text>
          </View>
        </View>
      </KeyboardAwareScroll>

      <View className="px-4 pb-6 pt-3 border-t border-border">
        <View className="w-full self-center" style={{ maxWidth: layout.reading }}>
          <Button size="lg" icon="checkmark-circle-outline" label="Place order" onPress={() => void handlePlaceOrder()} loading={loading} />
        </View>
      </View>
    </ScreenWrapper>
  );
}
