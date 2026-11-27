import { useState } from 'react';
import { useThemeColors } from '@/hooks/useThemeColors';
import { View, Text, FlatList, Pressable, RefreshControl, Share } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { ScreenWrapper } from '@/components/shared/ScreenWrapper';
import { Header } from '@/components/shared/Header';
import { ReportButton, ReportSheet } from '@/components/shared/ReportSheet';
import { useAuthStore } from '@/store/authStore';
import type { SocialPost } from '@/types';
import { AppImage } from '@/components/shared/AppImage';
import { Avatar } from '@/components/ui/Avatar';
import { Button } from '@/components/ui/Button';
import { useSocialFeed } from '@/hooks';
import { socialService } from '@/services';
import { hapticLight } from '@/utils/haptics';

export function SocialFeedScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<Record<string, object | undefined>>>();
  const { data: feed, isLoading, isError, refetch } = useSocialFeed();
  const [liked, setLiked] = useState<Record<string, boolean>>({});
  const palette = useThemeColors();
  const myId = useAuthStore((s) => s.user?.id);
  const [reporting, setReporting] = useState<SocialPost | null>(null);

  const toggleLike = async (id: string) => {
    setLiked((prev) => ({ ...prev, [id]: !prev[id] }));
    await socialService.toggleLike(id);
  };

  return (
    <ScreenWrapper loading={isLoading} error={isError ? 'Failed to load feed' : null} onRetry={refetch} empty={!feed?.length} emptyTitle="No looks yet" emptyMessage="Follow people whose style you like and their outfits will appear here.">
      <Header title="Community" showBack onBack={() => navigation.goBack()} />
      <ReportSheet
        visible={reporting !== null}
        onClose={() => setReporting(null)}
        target={reporting ? { type: 'post', id: reporting.id, label: 'this post' } : undefined}
        user={reporting ? { id: reporting.user.id, name: reporting.user.fullName } : undefined}
      />
      <FlatList
        data={feed}
        keyExtractor={(item) => item.id}
        refreshControl={<RefreshControl refreshing={isLoading} onRefresh={refetch} tintColor={palette.accent} />}
        renderItem={({ item }) => (
          <View className="mb-8 w-full self-center" style={{ maxWidth: 560 }}>
            <View className="flex-row items-center px-4 py-3">
              <Pressable
                accessibilityLabel={`View ${item.user.fullName}'s profile`}
                onPress={() => navigation.navigate('UserProfile', { userId: item.user.id })}
                className="flex-row items-center flex-1"
              >
                <Avatar uri={item.user.avatarUrl} name={item.user.fullName} size="sm" />
                <Text className="text-text-primary font-body-semibold ml-3">{item.user.fullName}</Text>
              </Pressable>
              <Button variant="secondary" size="sm" label="Follow" onPress={() => socialService.toggleFollow(item.user.id)} />
              {item.user.id !== myId && <ReportButton label={`Report or block ${item.user.fullName}`} onPress={() => setReporting(item)} />}
            </View>
            <Pressable accessibilityLabel="View outfit">
              <AppImage source={{ uri: item.outfitImageUrl }} className="w-full aspect-[4/5]" contentFit="cover" />
            </Pressable>
            <View className="flex-row items-center px-2 pt-1">
              <Pressable accessibilityRole="button" accessibilityLabel="Like" accessibilityState={{ selected: !!(liked[item.id] ?? item.liked) }} onPress={() => toggleLike(item.id)} className="flex-row items-center gap-1.5 min-h-11 px-2">
                <Ionicons name={liked[item.id] ?? item.liked ? 'heart' : 'heart-outline'} size={23} color={liked[item.id] ?? item.liked ? palette.accent : palette.textPrimary} />
                <Text className="text-text-primary font-body-medium text-sm tabular-nums">{item.likes + (liked[item.id] ? 1 : 0)}</Text>
              </Pressable>
              <Pressable accessibilityRole="button" accessibilityLabel="Comment" className="flex-row items-center gap-1.5 min-h-11 px-2">
                <Ionicons name="chatbubble-outline" size={21} color={palette.textPrimary} />
                <Text className="text-text-primary font-body-medium text-sm tabular-nums">{item.comments}</Text>
              </Pressable>
              <Pressable accessibilityRole="button" accessibilityLabel="Share" onPress={() => Share.share({ message: item.caption })} className="min-h-11 px-2 justify-center">
                <Ionicons name="paper-plane-outline" size={21} color={palette.textPrimary} />
              </Pressable>
            </View>
            <Text className="text-text-primary font-body text-base px-4 mb-3">
              <Text className="font-body-semibold">{item.user.fullName} </Text>
              {item.caption}
            </Text>
            {item.shopProductIds.length > 0 && (
              <Pressable
                accessibilityLabel="Shop this look"
                onPress={() => { hapticLight(); navigation.navigate('Marketplace'); }}
                className="mx-4 min-h-10 px-4 rounded-full border border-border-strong self-start flex-row items-center gap-2"
              >
                <Ionicons name="bag-outline" size={15} color={palette.textPrimary} />
                <Text className="text-text-primary font-body-medium text-sm">Shop this look</Text>
              </Pressable>
            )}
          </View>
        )}
      />
    </ScreenWrapper>
  );
}
