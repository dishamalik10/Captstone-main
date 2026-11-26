import { View, Text, FlatList, Pressable, RefreshControl } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { ScreenWrapper } from '@/components/shared/ScreenWrapper';
import { Header } from '@/components/shared/Header';
import { EmptyState } from '@/components/shared/EmptyState';
import { AppImage } from '@/components/shared/AppImage';
import { Avatar } from '@/components/ui/Avatar';
import { useConversations } from '@/hooks';
import { useRealtimeStore } from '@/store/realtimeStore';
import { useThemeColors } from '@/hooks/useThemeColors';
import type { Conversation } from '@/types';
import { cn } from '@/utils/helpers';
import { layout } from '@/constants/theme';

export function timeAgo(date: string) {
  const then = new Date(date).getTime();
  if (Number.isNaN(then)) return '';
  const minutes = Math.round((Date.now() - then) / 60000);
  if (minutes < 1) return 'now';
  if (minutes < 60) return `${minutes}m`;
  if (minutes < 60 * 24) return `${Math.round(minutes / 60)}h`;
  return new Date(date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
}

export function MessagesScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<Record<string, object | undefined>>>();
  const palette = useThemeColors();
  const { data, isLoading, isError, refetch, isRefetching } = useConversations();

  if (isLoading) return <ScreenWrapper loading />;
  if (isError) return <ScreenWrapper error="Could not load your messages" onRetry={refetch} />;
  const conversations = data?.conversations ?? [];

  return (
    <ScreenWrapper>
      <Header title="Messages" subtitle="Chats with buyers and sellers" showBack onBack={() => navigation.goBack()} />
      <FlatList
        data={conversations}
        keyExtractor={(item) => item.id}
        contentContainerStyle={{ paddingHorizontal: 16, paddingBottom: 48, width: '100%', maxWidth: layout.reading, alignSelf: 'center' }}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={palette.accent} />}
        ListEmptyComponent={
          <View className="min-h-[420px]">
            <EmptyState icon="chatbubbles-outline" title="No messages yet" message="Message a seller from any listing, or reply to buyers asking about your items." actionLabel="Browse the marketplace" onAction={() => navigation.navigate('Marketplace')} />
          </View>
        }
        renderItem={({ item }) => <ConversationRow conversation={item} onPress={() => navigation.navigate('Conversation', { id: item.id })} />}
      />
    </ScreenWrapper>
  );
}

function ConversationRow({ conversation, onPress }: { conversation: Conversation; onPress: () => void }) {
  const unread = conversation.unread > 0;
  const live = useRealtimeStore((s) => s.connected);
  const online = useRealtimeStore((s) => Boolean(s.online[conversation.otherUser.id])) || (!live && Boolean(conversation.otherUser.online));
  const typing = useRealtimeStore((s) => (s.typingUntil[conversation.id] ?? 0) > Date.now());
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${conversation.otherUser.name} about ${conversation.product.title}${unread ? `, ${conversation.unread} unread` : ''}`}
      onPress={onPress}
      className="flex-row items-center py-3 border-b border-border gap-3"
    >
      <View>
        <AppImage source={{ uri: conversation.product.imageUrl }} className="w-14 h-14 rounded-sm" contentFit="cover" />
        <View className="absolute -bottom-1 -right-1">
          <Avatar uri={conversation.otherUser.avatarUrl} name={conversation.otherUser.name} size="sm" />
          {online && (
            <View accessibilityLabel="Online" className="absolute bottom-0 right-0 w-3 h-3 rounded-full bg-success border-2 border-background" />
          )}
        </View>
      </View>
      <View className="flex-1 ml-1">
        <View className="flex-row items-baseline justify-between gap-2">
          <Text className={cn('text-text-primary text-base flex-1', unread ? 'font-body-semibold' : 'font-body-medium')} numberOfLines={1}>
            {conversation.otherUser.name}
          </Text>
          <Text className="text-text-tertiary font-body text-xs">{timeAgo(conversation.lastMessageAt)}</Text>
        </View>
        <Text className="text-text-secondary font-body text-xs" numberOfLines={1}>
          {conversation.role === 'seller' ? 'Buying your' : 'Selling'} {conversation.product.title}
          {conversation.product.status === 'sold' ? ' · sold' : ''}
        </Text>
        <Text className={cn('text-sm mt-0.5', unread ? 'text-text-primary font-body-medium' : 'text-text-secondary font-body')} numberOfLines={1}>
          {typing ? 'typing…' : conversation.lastMessage ? `${conversation.lastMessageMine ? 'You: ' : ''}${conversation.lastMessage}` : 'No messages yet'}
        </Text>
      </View>
      {unread && (
        <View className="min-w-[20px] h-5 px-1.5 rounded-full bg-accent items-center justify-center">
          <Text className="text-primary-ink font-body-semibold text-[11px] tabular-nums">{conversation.unread}</Text>
        </View>
      )}
    </Pressable>
  );
}
