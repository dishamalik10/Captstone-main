import { useState } from 'react';
import { View, Text, ScrollView, Pressable, RefreshControl } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { ScreenWrapper } from '@/components/shared/ScreenWrapper';
import { Header } from '@/components/shared/Header';
import { EmptyState } from '@/components/shared/EmptyState';
import { AppImage } from '@/components/shared/AppImage';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { useToastStore } from '@/components/ui/Toast';
import { useMyOrders, useRefreshMarketplace } from '@/hooks';
import { useThemeColors } from '@/hooks/useThemeColors';
import { marketplaceService } from '@/services';
import type { MarketOrder, OrderStatus } from '@/types';
import { formatCurrency } from '@/utils/helpers';
import { layout } from '@/constants/theme';
import { formatDay } from './SellerDashboardScreen';

type Nav = NativeStackNavigationProp<Record<string, object | undefined>>;

const STATUS: Record<OrderStatus, { label: string; note: string; variant: 'default' | 'success' | 'accent' }> = {
  pending: { label: 'Ordered', note: 'Waiting for the seller to ship', variant: 'accent' },
  shipped: { label: 'On its way', note: 'Shipped by the seller. Confirm when it arrives', variant: 'default' },
  completed: { label: 'Delivered', note: 'You confirmed delivery', variant: 'success' },
  cancelled: { label: 'Cancelled', note: 'This order was cancelled', variant: 'default' },
};

export function MyOrdersScreen() {
  const navigation = useNavigation<Nav>();
  const palette = useThemeColors();
  const { data: orders, isLoading, isError, refetch, isRefetching } = useMyOrders();

  if (isLoading) return <ScreenWrapper loading />;
  if (isError) return <ScreenWrapper error="Could not load your orders" onRetry={refetch} />;

  return (
    <ScreenWrapper>
      <Header title="My orders" subtitle="Pieces you bought on the marketplace" showBack onBack={() => navigation.goBack()} />
      <ScrollView
        className="flex-1 px-4"
        contentContainerStyle={{ paddingBottom: 48 }}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={palette.accent} />}
      >
        <View className="w-full self-center" style={{ maxWidth: layout.reading }}>
          {orders?.length ? orders.map((order) => <PurchaseCard key={order.id} order={order} />) : (
            <View className="min-h-[420px]">
              <EmptyState icon="bag-handle-outline" title="No orders yet" message="Pieces you buy from other AURA users show up here." actionLabel="Browse the marketplace" onAction={() => navigation.navigate('Marketplace')} />
            </View>
          )}
        </View>
      </ScrollView>
    </ScreenWrapper>
  );
}

function PurchaseCard({ order }: { order: MarketOrder }) {
  const navigation = useNavigation<Nav>();
  const showToast = useToastStore((s) => s.show);
  const refreshMarketplace = useRefreshMarketplace();
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const status = STATUS[order.status];

  const run = async (key: string, action: () => Promise<unknown>, success?: string) => {
    setBusy(key);
    try {
      await action();
      refreshMarketplace();
      if (success) showToast(success, 'success');
    } catch (error) {
      const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      showToast(typeof detail === 'string' ? detail : 'Something went wrong', 'error');
    } finally {
      setBusy(null);
    }
  };

  return (
    <View className="py-4 border-b border-border">
      <Pressable accessibilityRole="link" onPress={() => navigation.navigate('ProductDetail', { id: order.productId })} className="flex-row">
        <AppImage source={{ uri: order.imageUrl }} className="w-16 h-20 rounded-sm" contentFit="cover" />
        <View className="flex-1 ml-4">
          <View className="flex-row justify-between items-start gap-2">
            <Text className="text-text-primary font-body-medium text-base flex-1" numberOfLines={1}>{order.productTitle}</Text>
            <Badge label={status.label} variant={status.variant} />
          </View>
          <Text className="text-text-secondary font-body text-sm tabular-nums mt-0.5">
            {formatCurrency(order.amount)} · from {order.seller.name} · {formatDay(order.date)}
          </Text>
          <Text className="text-text-tertiary font-body text-xs mt-1">
            {status.note} · {order.paymentMethod === 'upi' ? 'UPI to seller' : 'Cash on delivery'}
          </Text>
        </View>
      </Pressable>
      <View className="flex-row flex-wrap gap-2 mt-3 ml-20">
        {order.status === 'shipped' && (
          <Button size="sm" icon="checkmark-done-outline" label="I received it" loading={busy === 'completed'}
            onPress={() => void run('completed', () => marketplaceService.updateOrderStatus(order.id, 'completed'), 'Enjoy your new piece!')} />
        )}
        <Button size="sm" variant="secondary" icon="chatbubble-outline" label="Message seller" loading={busy === 'message'}
          onPress={() => void run('message', async () => {
            const conversation = await marketplaceService.startConversation(order.productId);
            navigation.navigate('Conversation', { id: conversation.id });
          })} />
        {order.status === 'pending' && (
          <Button size="sm" variant="ghost" label="Cancel order" onPress={() => setConfirmCancel(true)} />
        )}
      </View>

      <Modal
        visible={confirmCancel}
        onClose={() => setConfirmCancel(false)}
        title="Cancel this order?"
        message="The seller is told, and the item goes back on sale."
        confirmLabel="Cancel order"
        cancelLabel="Keep order"
        destructive
        onConfirm={() => {
          setConfirmCancel(false);
          void run('cancelled', () => marketplaceService.updateOrderStatus(order.id, 'cancelled'), 'Order cancelled');
        }}
      />
    </View>
  );
}
