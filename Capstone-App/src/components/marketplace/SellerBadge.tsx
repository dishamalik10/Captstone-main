import { View, Text } from 'react-native';
import { Avatar } from '@/components/ui/Avatar';
import type { Seller } from '@/types';

interface SellerBadgeProps {
  seller: Seller;
}

function memberSince(date: string) {
  const parsed = new Date(date);
  return Number.isNaN(parsed.getTime())
    ? ''
    : `On AURA since ${parsed.toLocaleDateString('en-IN', { month: 'short', year: 'numeric' })}`;
}

export function SellerBadge({ seller }: SellerBadgeProps) {
  const sales = seller.sales === 0 ? 'New seller' : `${seller.sales} ${seller.sales === 1 ? 'sale' : 'sales'}`;
  return (
    <View className="flex-row items-center gap-3">
      <Avatar uri={seller.avatarUrl} name={seller.name} size="md" />
      <View className="flex-1">
        <Text className="text-text-primary font-body-semibold text-base">{seller.name}</Text>
        <Text className="text-text-secondary font-body text-xs mt-0.5">
          {[sales, memberSince(seller.memberSince)].filter(Boolean).join(' · ')}
        </Text>
      </View>
    </View>
  );
}
