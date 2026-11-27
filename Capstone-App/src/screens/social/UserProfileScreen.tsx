import { useState } from 'react';
import { View, Text, FlatList } from 'react-native';
import { useRoute, useNavigation } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import { useQuery } from '@tanstack/react-query';
import { ScreenWrapper } from '@/components/shared/ScreenWrapper';
import { Header } from '@/components/shared/Header';
import { Avatar } from '@/components/ui/Avatar';
import { Button } from '@/components/ui/Button';
import { socialService } from '@/services';
import { ReportButton, ReportSheet } from '@/components/shared/ReportSheet';
import { useAuthStore } from '@/store/authStore';

export function UserProfileScreen() {
  const route = useRoute<RouteProp<{ params: { userId: string } }>>();
  const navigation = useNavigation();
  const [following, setFollowing] = useState(false);
  const [reporting, setReporting] = useState(false);
  const myId = useAuthStore((s) => s.user?.id);
  const { data: user, isLoading, isError, refetch } = useQuery({
    queryKey: ['user', route.params.userId],
    queryFn: () => socialService.getUser(route.params.userId),
  });

  return (
    <ScreenWrapper loading={isLoading} error={isError ? 'User not found' : null} onRetry={refetch}>
      <Header showBack onBack={() => navigation.goBack()} rightAction={user && user.id !== myId ? <ReportButton onPress={() => setReporting(true)} /> : undefined} />
      {user && (
        <ReportSheet
          visible={reporting}
          onClose={() => setReporting(false)}
          target={{ type: 'user', id: user.id, label: user.fullName }}
          user={{ id: user.id, name: user.fullName }}
          onBlocked={() => navigation.goBack()}
        />
      )}
      {user && (
        <View className="px-5 w-full self-center" style={{ maxWidth: 640 }}>
          <View className="items-center py-6">
            <Avatar uri={user.avatarUrl} name={user.fullName} size="xl" />
            <Text accessibilityRole="header" className="text-text-primary font-display text-3xl mt-4">{user.fullName}</Text>
            <View className="flex-row mt-6 border-y border-border self-stretch">
              <View className="flex-1 py-4 items-center">
                <Text className="text-text-primary font-display text-2xl tabular-nums">{user.itemsCount}</Text>
                <Text className="text-text-secondary font-body text-xs">Pieces</Text>
              </View>
              <View className="flex-1 py-4 items-center border-l border-border">
                <Text className="text-text-primary font-display text-2xl tabular-nums">{user.followers}</Text>
                <Text className="text-text-secondary font-body text-xs">Followers</Text>
              </View>
              <View className="flex-1 py-4 items-center border-l border-border">
                <Text className="text-text-primary font-display text-2xl tabular-nums">{user.following}</Text>
                <Text className="text-text-secondary font-body text-xs">Following</Text>
              </View>
            </View>
            <Button
              variant={following ? 'secondary' : 'primary'}
              label={following ? 'Following' : 'Follow'}
              onPress={async () => {
                const result = await socialService.toggleFollow(route.params.userId);
                setFollowing(result.following);
              }}
              className="mt-6 w-44"
            />
          </View>
          <Text className="text-text-primary font-display text-2xl mb-2">Shared wardrobe</Text>
          <Text className="text-text-secondary font-body text-base">{user.fullName.split(' ')[0]} hasn’t shared any pieces publicly yet.</Text>
        </View>
      )}
    </ScreenWrapper>
  );
}
