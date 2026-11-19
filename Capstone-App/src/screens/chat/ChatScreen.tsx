import { useEffect, useState, useRef } from 'react';
import { FlatList, KeyboardAvoidingView, Platform, Pressable, View, Text } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { ScreenWrapper } from '@/components/shared/ScreenWrapper';
import { Header } from '@/components/shared/Header';
import { ChatBubble } from '@/components/chat/ChatBubble';
import { ChatInput } from '@/components/chat/ChatInput';
import { SuggestedReplies } from '@/components/chat/SuggestedReplies';
import { TypingIndicator } from '@/components/chat/TypingIndicator';
import { useChatStore } from '@/store/chatStore';
import { useThemeColors } from '@/hooks/useThemeColors';

export function ChatScreen() {
  const navigation = useNavigation<any>();
  const { messages, isTyping, sendMessage, loadMessages, newChat } = useChatStore();
  const [input, setInput] = useState('');
  const listRef = useRef<FlatList>(null);
  const palette = useThemeColors();

  useEffect(() => {
    void loadMessages();
  }, [loadMessages]);

  const handleSend = () => {
    if (!input.trim()) return;
    sendMessage(input.trim());
    setInput('');
    setTimeout(() => listRef.current?.scrollToEnd(), 100);
  };

  return (
    <ScreenWrapper>
      <Header
        title="Stylist chat"
        subtitle="Answers from your wardrobe"
        showBack
        onBack={() => navigation.goBack()}
        rightAction={
          <View className="flex-row -mr-1">
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Start new chat"
              onPress={newChat}
              className="w-11 h-11 items-center justify-center rounded-full hover:bg-surface-raised"
            >
              <Ionicons name="create-outline" size={21} color={palette.textPrimary} />
            </Pressable>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Go to home"
              onPress={() => navigation.navigate('Tabs', { screen: 'Home' })}
              className="w-11 h-11 items-center justify-center rounded-full hover:bg-surface-raised"
            >
              <Ionicons name="home-outline" size={20} color={palette.textPrimary} />
            </Pressable>
          </View>
        }
      />
      <KeyboardAvoidingView
        className="flex-1"
        style={{ paddingBottom: 82 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={90}
      >
        <FlatList
          ref={listRef}
          data={messages}
          keyExtractor={(item) => item.id}
          renderItem={({ item }) => <ChatBubble message={item} />}
          contentContainerStyle={{ paddingTop: 20, paddingBottom: 12, flexGrow: 1 }}
          ListEmptyComponent={
            <View className="flex-1 items-center justify-center px-8 py-12">
              <View className="w-24 h-24 rounded-full border border-border items-center justify-center mb-6">
                <View className="w-16 h-16 rounded-full bg-accent-soft items-center justify-center">
                  <Text className="font-display text-accent text-3xl">A</Text>
                </View>
              </View>
              <Text accessibilityRole="header" className="text-text-primary font-display text-3xl text-center">
                What are we dressing for?
              </Text>
              <Text className="text-text-secondary font-body text-base text-center mt-3 max-w-md">
                Ask for an occasion, a colour, a mood or a weather-ready look. Every answer starts from your own wardrobe.
              </Text>
            </View>
          }
          ListFooterComponent={isTyping ? <TypingIndicator /> : null}
          onContentSizeChange={() => listRef.current?.scrollToEnd()}
        />
        <SuggestedReplies onSelect={(text) => { setInput(text); sendMessage(text); }} />
        <ChatInput value={input} onChangeText={setInput} onSend={handleSend} />
      </KeyboardAvoidingView>
    </ScreenWrapper>
  );
}
