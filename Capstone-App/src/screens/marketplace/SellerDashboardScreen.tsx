import { useState } from 'react';
import { useNavigation } from '@react-navigation/native';
import { View, Text, ScrollView, Pressable } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { ScreenWrapper } from '@/components/shared/ScreenWrapper';
import { Header } from '@/components/shared/Header';
import { AppImage } from '@/components/shared/AppImage';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { marketplaceService } from '@/services';
import { formatCurrency } from '@/utils/helpers';
import { hapticLight } from '@/utils/haptics';

type Tab = 'listings' | 'orders' | 'earnings';

export function SellerDashboardScreen() {
  const [tab, setTab] = useState<Tab>('listings');
  const navigation = useNavigation();
  const { data: stats } = useQuery({ queryKey: ['seller-stats'], queryFn: () => marketplaceService.getSellerStats() });
  const { data: listings } = useQuery({ queryKey: ['seller-listings'], queryFn: () => marketplaceService.getSellerListings() });
  const { data: orders } = useQuery({ queryKey: ['seller-orders'], queryFn: () => marketplaceService.getSellerOrders() });

  return (
    <ScreenWrapper>
      <Header title="Seller dashboard" showBack onBack={() => navigation.goBack()} />
      <ScrollView className="flex-1 px-4" contentContainerStyle={{ paddingTop: 20, paddingBottom: 48 }}>
        {stats && (
          <View className="flex-row mb-8 border-y border-border">
            <View className="flex-1 py-4 pr-3">
              <Text className="text-text-primary font-display text-2xl tabular-nums">{stats.totalSales}</Text>
              <Text className="text-text-secondary font-body text-xs mt-0.5">Total sales</Text>
            </View>
            <View className="flex-1 py-4 px-3 border-l border-border">
              <Text className="text-text-primary font-display text-2xl tabular-nums" numberOfLines={1} adjustsFontSizeToFit>{formatCurrency(stats.revenue)}</Text>
              <Text className="text-text-secondary font-body text-xs mt-0.5">Revenue</Text>
            </View>
            <View className="flex-1 py-4 pl-3 border-l border-border">
              <Text className="text-text-primary font-display text-2xl tabular-nums">{stats.activeListings}</Text>
              <Text className="text-text-secondary font-body text-xs mt-0.5">Active listings</Text>
            </View>
          </View>
        )}

        <View className="flex-row mb-4 border-b border-border" accessibilityRole="tablist">
          {(['listings', 'orders', 'earnings'] as Tab[]).map((t) => (
            <Pressable
              key={t}
              accessibilityRole="tab"
              accessibilityState={{ selected: tab === t }}
              onPress={() => { hapticLight(); setTab(t); }}
              className={`flex-1 min-h-12 items-center justify-center border-b-2 -mb-px ${tab === t ? 'border-primary' : 'border-transparent'}`}
            >
              <Text className={`text-base capitalize ${tab === t ? 'text-text-primary font-body-medium' : 'text-text-secondary font-body'}`}>{t}</Text>
            </Pressable>
          ))}
        </View>

        {tab === 'listings' && listings?.map((l) => (
          <View key={l.id} className="flex-row items-center py-3 border-b border-border">
            <AppImage source={{ uri: l.imageUrl }} className="w-14 h-16 rounded-sm" contentFit="cover" />
            <View className="flex-1 ml-4">
              <Text className="text-text-primary font-body-medium text-base">{l.title}</Text>
              <Text className="text-text-secondary font-body text-sm tabular-nums">{formatCurrency(l.price)}</Text>
            </View>
            <Badge label={l.status} variant={l.status === 'active' ? 'success' : 'default'} />
          </View>
        ))}

        {tab === 'orders' && orders?.map((o) => (
          <View key={o.id} className="py-4 border-b border-border">
            <View className="flex-row justify-between items-center">
              <Text className="text-text-primary font-body-medium text-base">{o.productTitle}</Text>
              <Badge label={o.status} variant={o.status === 'completed' ? 'success' : 'default'} />
            </View>
            <View className="flex-row justify-between mt-1">
              <Text className="text-text-secondary font-body text-sm">{o.date}</Text>
              <Text className="text-text-primary font-body text-sm tabular-nums">{formatCurrency(o.amount)}</Text>
            </View>
          </View>
        ))}

        {tab === 'earnings' && stats && (
          <View className="items-center py-8">
            <Text className="text-text-secondary font-body mb-2">Total earnings</Text>
            <Text className="text-text-primary font-display text-5xl mb-2 tabular-nums" style={{ lineHeight: 56 }}>{formatCurrency(stats.revenue)}</Text>
            <Text className="text-text-tertiary font-body text-sm mb-8">Across {stats.totalSales} sales</Text>
            <Button label="Request payout" onPress={() => {}} />
          </View>
        )}
      </ScrollView>
    </ScreenWrapper>
  );
}
