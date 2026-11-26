import { useEffect, useRef, useState } from 'react';
import { View, Text, FlatList, Pressable, TextInput, KeyboardAvoidingView, Platform } from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useQueryClient } from '@tanstack/react-query';
import { Ionicons } from '@expo/vector-icons';
import { ScreenWrapper } from '@/components/shared/ScreenWrapper';
import { Header } from '@/components/shared/Header';
import { AppImage } from '@/components/shared/AppImage';
import { useToastStore } from '@/components/ui/Toast';
import { useConversation } from '@/hooks';
import { sendTyping } from '@/hooks/useRealtime';
import { useRealtimeStore } from '@/store/realtimeStore';
import { useThemeColors } from '@/hooks/useThemeColors';
import { marketplaceService } from '@/services';
import type { MarketMessage } from '@/types';
import { cn, formatCurrency } from '@/utils/helpers';
import { layout } from '@/constants/theme';

const QUICK_REPLIES = {
  buyer: ['Is this still available?', 'Can you share more photos?', 'Would you take a lower price?'],
  seller: ['Yes, it’s available!', 'I’ll ship it tomorrow', 'My UPI ID is '],
};

function clock(date: string) {
  const parsed = new Date(date);
  return Number.isNaN(parsed.getTime()) ? '' : parsed.toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit' });
}

export function ConversationScreen() {
  const route = useRoute<RouteProp<{ params: { id: string } }>>();
  const navigation = useNavigation<NativeStackNavigationProp<Record<string, object | undefined>>>();
  const palette = useThemeColors();
  const queryClient = useQueryClient();
  const showToast = useToastStore((s) => s.show);
  const { data, isLoading, isError, refetch } = useConversation(route.params.id);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const listRef = useRef<FlatList<MarketMessage>>(null);
  const messages = data?.messages ?? [];
  const otherId = data?.conversation.otherUser.id;
  const online = useRealtimeStore((s) => (otherId ? Boolean(s.online[otherId]) : false));
  const typingUntil = useRealtimeStore((s) => s.typingUntil[route.params.id] ?? 0);
  const [now, setNow] = useState(Date.now());
  const typing = typingUntil > now;

  // Re-render when the "typing…" window expires.
  useEffect(() => {
    if (typingUntil <= Date.now()) return undefined;
    const timer = setTimeout(() => setNow(Date.now()), typingUntil - Date.now() + 50);
    setNow(Date.now());
    return () => clearTimeout(timer);
  }, [typingUntil]);

  // Opening the thread marks it read: refresh the inbox badge.
  useEffect(() => {
    if (data) void queryClient.invalidateQueries({ queryKey: ['conversations'] });
  }, [data?.messages.length, queryClient]); // eslint-disable-line react-hooks/exhaustive-deps

  if (isLoading) return <ScreenWrapper loading />;
  if (isError || !data) return <ScreenWrapper error="Could not open this chat" onRetry={refetch} />;
  const { conversation } = data;

  const send = async (text = draft) => {
    const body = text.trim();
    if (!body || sending) return;
    setSending(true);
    try {
      const message = await marketplaceService.sendMessage(conversation.id, body);
      queryClient.setQueryData(['conversation', conversation.id], { conversation, messages: [...messages, message] });
      setDraft('');
      void queryClient.invalidateQueries({ queryKey: ['conversations'] });
    } catch {
      showToast('Message not sent. Try again', 'error');
    } finally {
      setSending(false);
    }
  };

  return (
    <ScreenWrapper>
      <Header
        title={conversation.otherUser.name}
        subtitle={typing ? 'typing…' : online ? 'Online' : conversation.role === 'seller' ? 'Interested in your listing' : 'Seller'}
        showBack
        onBack={() => navigation.goBack()}
      />
      <Pressable
        accessibilityRole="link"
        accessibilityLabel={`View listing ${conversation.product.title}`}
        onPress={() => navigation.navigate('ProductDetail', { id: conversation.product.id })}
        className="flex-row items-center gap-3 px-4 py-2.5 border-b border-border bg-surface"
      >
        <AppImage source={{ uri: conversation.product.imageUrl }} className="w-10 h-12 rounded-sm" contentFit="cover" />
        <View className="flex-1">
          <Text className="text-text-primary font-body-medium text-sm" numberOfLines={1}>{conversation.product.title}</Text>
          <Text className="text-text-secondary font-body text-xs tabular-nums">
            {formatCurrency(conversation.product.price)}{conversation.product.status === 'sold' ? ' · Sold' : conversation.product.status === 'paused' ? ' · Paused' : ''}
          </Text>
        </View>
        <Ionicons name="chevron-forward" size={16} color={palette.textTertiary} />
      </Pressable>

      <KeyboardAvoidingView className="flex-1" behavior={Platform.OS === 'ios' ? 'padding' : undefined} keyboardVerticalOffset={90}>
        <FlatList
          ref={listRef}
          data={messages}
          keyExtractor={(item) => item.id}
          contentContainerStyle={{ padding: 16, gap: 8, flexGrow: 1, width: '100%', maxWidth: layout.reading, alignSelf: 'center' }}
          onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: false })}
          ListFooterComponent={typing ? (
            <View className="self-start px-3.5 py-2.5 rounded-2xl rounded-bl-sm bg-surface-raised border border-border">
              <Text className="text-text-secondary font-body text-sm">typing…</Text>
            </View>
          ) : null}
          ListEmptyComponent={
            <View className="flex-1 items-center justify-center py-16 px-6">
              <Ionicons name="chatbubbles-outline" size={28} color={palette.textTertiary} />
              <Text className="text-text-secondary font-body text-sm text-center mt-3">
                {conversation.role === 'buyer'
                  ? `Ask ${conversation.otherUser.name} about size, condition or delivery.`
                  : `Say hello to ${conversation.otherUser.name}.`}
              </Text>
            </View>
          }
          renderItem={({ item }) => (
            <View className={cn('max-w-[80%]', item.mine ? 'self-end items-end' : 'self-start items-start')}>
              <View className={cn('px-3.5 py-2.5 rounded-2xl', item.mine ? 'bg-primary rounded-br-sm' : 'bg-surface-raised border border-border rounded-bl-sm')}>
                <Text className={cn('font-body text-base', item.mine ? 'text-primary-ink' : 'text-text-primary')}>{item.body}</Text>
              </View>
              <Text className="text-text-tertiary font-body text-[11px] mt-1 px-1">
                {clock(item.createdAt)}{item.mine && item.read ? ' · Seen' : ''}
              </Text>
            </View>
          )}
        />

        <View className="border-t border-border px-4 pt-2 pb-5 bg-background">
          <View className="w-full self-center" style={{ maxWidth: layout.reading }}>
            {messages.length < 2 && (
              <View className="flex-row flex-wrap gap-2 mb-2">
                {QUICK_REPLIES[conversation.role].map((reply) => (
                  <Pressable
                    key={reply}
                    accessibilityRole="button"
                    onPress={() => (reply.endsWith(' ') ? setDraft(reply) : void send(reply))}
                    className="px-3 py-1.5 rounded-full border border-border"
                  >
                    <Text className="text-text-secondary font-body text-sm">{reply.trim()}</Text>
                  </Pressable>
                ))}
              </View>
            )}
            <View className="flex-row items-end gap-2">
              <TextInput
                value={draft}
                onChangeText={(text) => {
                  setDraft(text);
                  if (text.trim()) sendTyping(conversation.id);
                }}
                placeholder="Write a message"
                placeholderTextColor={palette.textTertiary}
                selectionColor={palette.accent}
                multiline
                maxLength={2000}
                accessibilityLabel="Message"
                onKeyPress={(e) => {
                  // Enter sends on web; Shift+Enter adds a line.
                  const native = e.nativeEvent as { key: string; shiftKey?: boolean };
                  if (Platform.OS === 'web' && native.key === 'Enter' && !native.shiftKey) {
                    (e as unknown as { preventDefault?: () => void }).preventDefault?.();
                    void send();
                  }
                }}
                className="flex-1 min-h-11 max-h-32 px-4 py-2.5 rounded-3xl border border-border bg-surface text-text-primary font-body text-base"
              />
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Send message"
                disabled={!draft.trim() || sending}
                onPress={() => void send()}
                className={cn('w-11 h-11 rounded-full bg-primary items-center justify-center', (!draft.trim() || sending) && 'opacity-40')}
              >
                <Ionicons name="arrow-up" size={20} color={palette.primaryInk} />
              </Pressable>
            </View>
          </View>
        </View>
      </KeyboardAvoidingView>
    </ScreenWrapper>
  );
}
