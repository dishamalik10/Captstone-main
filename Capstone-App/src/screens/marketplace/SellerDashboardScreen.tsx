import { useState } from 'react';
import { View, Text, ScrollView, Pressable, TextInput, RefreshControl } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { ScreenWrapper } from '@/components/shared/ScreenWrapper';
import { Header } from '@/components/shared/Header';
import { EmptyState } from '@/components/shared/EmptyState';
import { AppImage } from '@/components/shared/AppImage';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { useToastStore } from '@/components/ui/Toast';
import { useRefreshMarketplace, useSellerDashboard } from '@/hooks';
import { useThemeColors } from '@/hooks/useThemeColors';
import { marketplaceService } from '@/services';
import type { MarketOrder, OrderStatus, Product } from '@/types';
import { cn, formatCurrency } from '@/utils/helpers';
import { hapticLight } from '@/utils/haptics';
import { layout } from '@/constants/theme';

type Tab = 'listings' | 'orders';
type Nav = NativeStackNavigationProp<Record<string, object | undefined>>;

const ORDER_STATUS: Record<OrderStatus, { label: string; variant: 'default' | 'success' | 'accent' }> = {
  pending: { label: 'New order', variant: 'accent' },
  shipped: { label: 'Shipped', variant: 'default' },
  completed: { label: 'Delivered', variant: 'success' },
  cancelled: { label: 'Cancelled', variant: 'default' },
};

function errorDetail(error: unknown, fallback: string) {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof detail === 'string' ? detail : fallback;
}

export function formatDay(date: string) {
  const parsed = new Date(date);
  return Number.isNaN(parsed.getTime()) ? date : parsed.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
}

export function SellerDashboardScreen() {
  const [tab, setTab] = useState<Tab>('listings');
  const navigation = useNavigation<Nav>();
  const palette = useThemeColors();
  const { data, isLoading, isError, refetch, isRefetching } = useSellerDashboard();
  const pending = data?.stats.pendingOrders ?? 0;

  if (isLoading) return <ScreenWrapper loading />;
  if (isError || !data) return <ScreenWrapper error="Could not load your seller dashboard" onRetry={refetch} />;
  const { stats, listings, orders } = data;

  return (
    <ScreenWrapper>
      <Header title="Seller dashboard" showBack onBack={() => navigation.goBack()} />
      <ScrollView
        className="flex-1 px-4"
        contentContainerStyle={{ paddingTop: 16, paddingBottom: 48 }}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={palette.accent} />}
      >
        <View className="w-full self-center" style={{ maxWidth: layout.reading }}>
          <View className="flex-row flex-wrap border-y border-border mb-4">
            <Stat value={String(stats.totalSales)} label="Sales" />
            <Stat value={formatCurrency(stats.revenue)} label="Earned" divider />
            <Stat value={String(stats.activeListings)} label="Live listings" divider />
            <Stat value={String(pending)} label="New orders" divider highlight={pending > 0} />
          </View>

          <View className="flex-row gap-3 mb-6">
            <View className="flex-1">
              <Button icon="add" label="Sell an item" onPress={() => navigation.navigate('SellItem')} />
            </View>
            <View className="flex-1">
              <Button
                variant="secondary"
                icon="chatbubbles-outline"
                label={stats.unreadMessages ? `Messages (${stats.unreadMessages})` : 'Messages'}
                onPress={() => navigation.navigate('Messages')}
              />
            </View>
          </View>

          <View className="flex-row mb-2 border-b border-border" accessibilityRole="tablist">
            {(['listings', 'orders'] as Tab[]).map((t) => (
              <Pressable
                key={t}
                accessibilityRole="tab"
                accessibilityState={{ selected: tab === t }}
                onPress={() => { hapticLight(); setTab(t); }}
                className={cn('flex-1 min-h-12 items-center justify-center border-b-2 -mb-px', tab === t ? 'border-primary' : 'border-transparent')}
              >
                <Text className={cn('text-base', tab === t ? 'text-text-primary font-body-medium' : 'text-text-secondary font-body')}>
                  {t === 'listings' ? `Listings (${listings.length})` : `Orders${pending ? ` · ${pending} new` : ''}`}
                </Text>
              </Pressable>
            ))}
          </View>

          {tab === 'listings' && (listings.length ? listings.map((listing) => (
            <ListingRow key={listing.id} listing={listing} />
          )) : (
            <View className="min-h-[300px]">
              <EmptyState icon="pricetag-outline" title="Nothing for sale yet" message="List a piece you no longer wear. It takes a minute." actionLabel="Sell an item" onAction={() => navigation.navigate('SellItem')} />
            </View>
          ))}

          {tab === 'orders' && (orders.length ? orders.map((order) => (
            <OrderCard key={order.id} order={order} />
          )) : (
            <View className="min-h-[300px]">
              <EmptyState icon="receipt-outline" title="No orders yet" message="When someone buys one of your listings, it shows up here." />
            </View>
          ))}
        </View>
      </ScrollView>
    </ScreenWrapper>
  );
}

function Stat({ value, label, divider, highlight }: { value: string; label: string; divider?: boolean; highlight?: boolean }) {
  return (
    <View className={cn('w-1/4 py-4 px-2', divider && 'border-l border-border')}>
      <Text className={cn('font-display text-xl tabular-nums', highlight ? 'text-accent' : 'text-text-primary')} numberOfLines={1} adjustsFontSizeToFit>
        {value}
      </Text>
      <Text className="text-text-secondary font-body text-xs mt-0.5">{label}</Text>
    </View>
  );
}

function ListingRow({ listing }: { listing: Product }) {
  const navigation = useNavigation<Nav>();
  const palette = useThemeColors();
  const showToast = useToastStore((s) => s.show);
  const refreshMarketplace = useRefreshMarketplace();
  const [editingPrice, setEditingPrice] = useState(false);
  const [price, setPrice] = useState(String(listing.price));
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const run = async (action: () => Promise<unknown>, success: string, failure: string) => {
    setBusy(true);
    try {
      await action();
      refreshMarketplace();
      showToast(success, 'success');
      return true;
    } catch (error) {
      showToast(errorDetail(error, failure), 'error');
      return false;
    } finally {
      setBusy(false);
    }
  };

  const savePrice = async () => {
    const value = Number(price.replace(/[^\d.]/g, ''));
    if (!value) return showToast('Enter a price above zero', 'error');
    if (await run(() => marketplaceService.updateListing(listing.id, { price: value }), 'Price updated', 'Could not update the price')) {
      setEditingPrice(false);
    }
  };

  return (
    <View className="py-3 border-b border-border">
      <Pressable onPress={() => navigation.navigate('ProductDetail', { id: listing.id })} accessibilityRole="link" className="flex-row items-center">
        <AppImage source={{ uri: listing.imageUrls[0] }} className="w-14 h-16 rounded-sm" contentFit="cover" />
        <View className="flex-1 ml-4">
          <Text className="text-text-primary font-body-medium text-base" numberOfLines={1}>{listing.title}</Text>
          {!editingPrice && <Text className="text-text-secondary font-body text-sm tabular-nums">{formatCurrency(listing.price)}{listing.size ? ` · Size ${listing.size}` : ''}</Text>}
        </View>
        <Badge label={listing.status === 'active' ? 'Live' : listing.status === 'sold' ? 'Sold' : 'Paused'} variant={listing.status === 'active' ? 'success' : 'default'} />
      </Pressable>

      {editingPrice ? (
        <View className="flex-row items-center gap-2 mt-3">
          <View className="flex-1 flex-row items-center px-3 h-11 rounded-sm border border-border bg-surface">
            <Text className="text-text-secondary font-body text-base">₹</Text>
            <TextInput
              value={price}
              onChangeText={setPrice}
              keyboardType="number-pad"
              autoFocus
              accessibilityLabel="New price"
              onSubmitEditing={() => void savePrice()}
              className="flex-1 ml-1 text-text-primary font-body text-base"
            />
          </View>
          <Button size="sm" label="Save" loading={busy} onPress={() => void savePrice()} />
          <Button size="sm" variant="ghost" label="Cancel" onPress={() => { setEditingPrice(false); setPrice(String(listing.price)); }} />
        </View>
      ) : listing.status !== 'sold' && (
        <View className="flex-row gap-5 mt-2 ml-[72px]">
          <RowAction icon="create-outline" label="Edit price" onPress={() => setEditingPrice(true)} />
          <RowAction
            icon={listing.status === 'active' ? 'pause-outline' : 'play-outline'}
            label={listing.status === 'active' ? 'Pause' : 'Relist'}
            onPress={() => void run(
              () => marketplaceService.updateListing(listing.id, { status: listing.status === 'active' ? 'paused' : 'active' }),
              listing.status === 'active' ? 'Listing paused' : 'Listing is live again',
              'Could not update the listing',
            )}
          />
          <RowAction icon="trash-outline" label="Delete" color={palette.destructive} onPress={() => setConfirmDelete(true)} />
        </View>
      )}

      <Modal
        visible={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        title="Delete this listing?"
        message={`“${listing.title}” and its photos will be removed. Listings that already have orders can only be paused.`}
        confirmLabel="Delete"
        destructive
        onConfirm={() => {
          setConfirmDelete(false);
          void run(() => marketplaceService.deleteListing(listing.id), 'Listing deleted', 'Could not delete the listing');
        }}
      />
    </View>
  );
}

function RowAction({ icon, label, onPress, color }: { icon: keyof typeof Ionicons.glyphMap; label: string; onPress: () => void; color?: string }) {
  const palette = useThemeColors();
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={label} onPress={onPress} hitSlop={8} className="flex-row items-center gap-1">
      <Ionicons name={icon} size={15} color={color ?? palette.textSecondary} />
      <Text className="font-body text-sm" style={{ color: color ?? palette.textSecondary }}>{label}</Text>
    </Pressable>
  );
}

function OrderCard({ order }: { order: MarketOrder }) {
  const navigation = useNavigation<Nav>();
  const showToast = useToastStore((s) => s.show);
  const refreshMarketplace = useRefreshMarketplace();
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmDecline, setConfirmDecline] = useState(false);
  const status = ORDER_STATUS[order.status];
  const address = order.shippingAddress;

  const setStatus = async (next: 'shipped' | 'cancelled') => {
    setBusy(next);
    try {
      await marketplaceService.updateOrderStatus(order.id, next);
      refreshMarketplace();
      showToast(next === 'shipped' ? 'Marked as shipped. The buyer can now confirm delivery' : 'Order declined. The item is back on sale', 'success');
    } catch (error) {
      showToast(errorDetail(error, 'Could not update the order'), 'error');
    } finally {
      setBusy(null);
    }
  };

  const messageBuyer = async () => {
    setBusy('message');
    try {
      const conversation = await marketplaceService.startConversation(order.productId, order.buyer.id);
      navigation.navigate('Conversation', { id: conversation.id });
    } catch (error) {
      showToast(errorDetail(error, 'Could not open the chat'), 'error');
    } finally {
      setBusy(null);
    }
  };

  return (
    <View className="py-4 border-b border-border">
      <View className="flex-row">
        <AppImage source={{ uri: order.imageUrl }} className="w-14 h-16 rounded-sm" contentFit="cover" />
        <View className="flex-1 ml-4">
          <View className="flex-row justify-between items-start gap-2">
            <Text className="text-text-primary font-body-medium text-base flex-1" numberOfLines={1}>{order.productTitle}</Text>
            <Badge label={status.label} variant={status.variant} />
          </View>
          <Text className="text-text-secondary font-body text-sm tabular-nums mt-0.5">
            {formatCurrency(order.amount)} · {order.paymentMethod === 'upi' ? 'UPI' : 'Cash on delivery'} · {formatDay(order.date)}
          </Text>
          <Text className="text-text-primary font-body text-sm mt-2">Buyer: {order.buyer.name}</Text>
          {!!address.line1 && (
            <Text className="text-text-secondary font-body text-sm mt-0.5">
              {[address.name, address.phone].filter(Boolean).join(' · ')}{'\n'}
              {[address.line1, address.city, address.pincode].filter(Boolean).join(', ')}
            </Text>
          )}
        </View>
      </View>
      <View className="flex-row flex-wrap gap-2 mt-3 ml-[72px]">
        {order.status === 'pending' && (
          <>
            <Button size="sm" icon="cube-outline" label="Mark shipped" loading={busy === 'shipped'} onPress={() => void setStatus('shipped')} />
            <Button size="sm" variant="ghost" label="Decline" onPress={() => setConfirmDecline(true)} />
          </>
        )}
        <Button size="sm" variant="secondary" icon="chatbubble-outline" label="Message buyer" loading={busy === 'message'} onPress={() => void messageBuyer()} />
      </View>

      <Modal
        visible={confirmDecline}
        onClose={() => setConfirmDecline(false)}
        title="Decline this order?"
        message={`${order.buyer.name}’s order is cancelled and “${order.productTitle}” goes back on sale.`}
        confirmLabel="Decline order"
        destructive
        onConfirm={() => {
          setConfirmDecline(false);
          void setStatus('cancelled');
        }}
      />
    </View>
  );
}
