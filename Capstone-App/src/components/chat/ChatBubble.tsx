import { useState } from 'react';
import { Modal, Pressable, View, Text } from 'react-native';
import Animated, { FadeInUp } from 'react-native-reanimated';
import { Ionicons } from '@expo/vector-icons';
import { AppImage } from '@/components/shared/AppImage';
import type { ChatMessage } from '@/types';
import { OutfitCard } from '@/components/outfits/OutfitCard';
import { ProductCard } from '@/components/marketplace/ProductCard';
import { cn } from '@/utils/helpers';
import { landing, motion, withAlpha } from '@/constants/theme';

interface ChatBubbleProps {
  message: ChatMessage;
}

/** The stylist's mark: a small monogram, never a stranger's photograph. */
function StylistMark() {
  return (
    <View className="w-8 h-8 rounded-full border border-accent/50 bg-accent-soft items-center justify-center">
      <Text className="font-display text-accent text-sm">A</Text>
    </View>
  );
}

export function ChatBubble({ message }: ChatBubbleProps) {
  const isUser = message.role === 'user';
  const [imageOpen, setImageOpen] = useState(false);

  return (
    <Animated.View
      entering={FadeInUp.duration(motion.short)}
      className={cn('mb-5 px-4', isUser ? 'items-end' : 'items-start')}
    >
      <View className={cn('flex-row items-end gap-2.5', isUser ? 'max-w-[82%]' : 'max-w-[88%]')}>
        {!isUser && <StylistMark />}
        <View className="flex-shrink">
          {!isUser && <Text className="text-accent font-body-medium text-xs mb-1 ml-1">AURA stylist</Text>}
          <View
            className={cn(
              'px-4 py-3',
              isUser
                ? 'bg-surface-raised rounded-2xl rounded-br-sm'
                : 'bg-surface border border-border rounded-2xl rounded-bl-sm',
            )}
          >
            <Text className="font-body text-base text-text-primary">{message.content}</Text>
            {message.outfit && (
              <View className="mt-3 min-w-[220px]">
                <OutfitCard outfit={message.outfit} compact onPress={() => setImageOpen(true)} />
              </View>
            )}
            {message.product && (
              <View className="mt-3 min-w-[180px]">
                <ProductCard product={message.product} compact />
              </View>
            )}
            {message.colorPalette && (
              <View className="flex-row gap-2 mt-3">
                {message.colorPalette.map((color) => (
                  <View
                    key={color}
                    accessibilityLabel={`Colour ${color}`}
                    className="w-8 h-8 rounded-full border border-border-strong"
                    style={{ backgroundColor: color }}
                  />
                ))}
              </View>
            )}
          </View>
        </View>
      </View>
      {message.outfit && (
        <Modal visible={imageOpen} transparent animationType="fade" onRequestClose={() => setImageOpen(false)}>
          <View
            className="flex-1 items-center justify-center p-6"
            style={{ backgroundColor: withAlpha(landing.night, 0.96) }}
          >
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Close outfit image"
              onPress={() => setImageOpen(false)}
              className="absolute top-12 right-6 z-10 w-11 h-11 rounded-full items-center justify-center border"
              style={{ borderColor: landing.nightRule }}
            >
              <Ionicons name="close" size={22} color={landing.inkPaper} />
            </Pressable>
            <AppImage
              source={{ uri: message.outfit.imageUrl }}
              className="w-full max-w-4xl h-[78%] rounded-md"
              contentFit="contain"
            />
            <Text className="font-display text-2xl mt-5 text-center" style={{ color: landing.inkPaper }}>
              {message.outfit.name}
            </Text>
            <Text className="font-body text-sm mt-1 text-center" style={{ color: landing.nightMuted }}>
              Ranked by rule-based signals (uncalibrated)
            </Text>
          </View>
        </Modal>
      )}
    </Animated.View>
  );
}
