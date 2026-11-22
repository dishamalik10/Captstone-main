import { useState } from 'react';
import { Modal, Pressable, View, Text } from 'react-native';
import Animated, { FadeInUp } from 'react-native-reanimated';
import { Ionicons } from '@expo/vector-icons';
import { AppImage } from '@/components/shared/AppImage';
import type { ChatMessage } from '@/types';
import { OutfitCard } from '@/components/outfits/OutfitCard';
import { OutfitCollage } from '@/components/outfits/OutfitCollage';
import { ProductCard } from '@/components/marketplace/ProductCard';
import { cn } from '@/utils/helpers';
import { useOutfitAI } from '@/hooks';
import { useThemeColors } from '@/hooks/useThemeColors';
import { hapticLight } from '@/utils/haptics';
import type { Outfit } from '@/types';
import { landing, motion, withAlpha } from '@/constants/theme';

interface ChatBubbleProps {
  message: ChatMessage;
}

type Reaction = 'like' | 'dislike' | 'wear';

const REACTIONS: { action: Reaction; icon: keyof typeof Ionicons.glyphMap; activeIcon: keyof typeof Ionicons.glyphMap; label: string }[] = [
  { action: 'like', icon: 'thumbs-up-outline', activeIcon: 'thumbs-up', label: 'Like' },
  { action: 'dislike', icon: 'thumbs-down-outline', activeIcon: 'thumbs-down', label: 'Not for me' },
  { action: 'wear', icon: 'checkmark-circle-outline', activeIcon: 'checkmark-circle', label: 'Wore it' },
];

/** Reactions on a suggested outfit; each one trains the user's personal ranking model. */
function OutfitFeedback({ outfit }: { outfit: Outfit }) {
  const { feedbackMutation } = useOutfitAI();
  const palette = useThemeColors();
  const [chosen, setChosen] = useState<Reaction | null>(null);

  const react = (action: Reaction) => {
    if (chosen || feedbackMutation.isPending) return;
    hapticLight();
    feedbackMutation.mutate({ outfit, action }, { onSuccess: () => setChosen(action) });
  };

  return (
    <View className="mt-2">
      <View className="flex-row gap-2">
        {REACTIONS.map(({ action, icon, activeIcon, label }) => {
          const active = chosen === action;
          return (
            <Pressable
              key={action}
              accessibilityRole="button"
              accessibilityLabel={label}
              accessibilityState={{ selected: active, disabled: chosen !== null && !active }}
              disabled={chosen !== null || feedbackMutation.isPending}
              onPress={() => react(action)}
              className={cn(
                'flex-row items-center gap-1.5 rounded-full border px-3 py-1.5',
                active ? 'border-accent bg-accent-soft' : 'border-border',
                chosen !== null && !active && 'opacity-40',
              )}
            >
              <Ionicons name={active ? activeIcon : icon} size={15} color={active ? palette.accent : palette.textSecondary} />
              <Text className={cn('font-body-medium text-xs', active ? 'text-accent' : 'text-text-secondary')}>{label}</Text>
            </Pressable>
          );
        })}
      </View>
      {chosen && (
        <Text className="font-body text-xs text-text-tertiary mt-1.5 ml-1">
          Thanks — I'll use this to tailor your next suggestions.
        </Text>
      )}
      {feedbackMutation.isError && (
        <Text className="font-body text-xs text-destructive mt-1.5 ml-1">Couldn't save that. Try again.</Text>
      )}
    </View>
  );
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
                <OutfitFeedback outfit={message.outfit} />
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
            <View className="w-full max-w-4xl h-[78%] rounded-md overflow-hidden">
              <OutfitCollage outfit={message.outfit} contentFit="contain" />
            </View>
            <Text className="font-display text-2xl mt-5 text-center" style={{ color: landing.inkPaper }}>
              {message.outfit.name}
            </Text>
            <Text className="font-body text-sm mt-1 text-center" style={{ color: landing.nightMuted }}>
              {message.outfit.itemImages?.map((piece) => piece.label).join(' + ')}
            </Text>
          </View>
        </Modal>
      )}
    </Animated.View>
  );
}
