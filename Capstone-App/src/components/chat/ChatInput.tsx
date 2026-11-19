import { View, TextInput, Pressable } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { hapticLight } from '@/utils/haptics';
import { cn } from '@/utils/helpers';
import { useThemeColors } from '@/hooks/useThemeColors';

interface ChatInputProps {
  value: string;
  onChangeText: (text: string) => void;
  onSend: () => void;
  onAttach?: () => void;
}

export function ChatInput({ value, onChangeText, onSend, onAttach }: ChatInputProps) {
  const palette = useThemeColors();
  const canSend = !!value.trim();
  return (
    <View className="flex-row items-end mx-4 mb-3 pl-1 pr-1.5 py-1.5 border border-border bg-surface rounded-3xl gap-1">
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Attach image"
        onPress={() => {
          hapticLight();
          onAttach?.();
        }}
        className="w-11 h-11 items-center justify-center rounded-full hover:bg-surface-raised"
      >
        <Ionicons name="image-outline" size={22} color={palette.textSecondary} />
      </Pressable>
      <TextInput
        accessibilityLabel="Message your stylist"
        value={value}
        onChangeText={onChangeText}
        placeholder="Ask your stylist…"
        placeholderTextColor={palette.textTertiary}
        selectionColor={palette.accent}
        className="flex-1 px-1 py-3 text-text-primary font-body text-base max-h-32"
        multiline
      />
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Send message"
        accessibilityState={{ disabled: !canSend }}
        onPress={() => {
          hapticLight();
          onSend();
        }}
        disabled={!canSend}
        className={cn(
          'w-11 h-11 rounded-full items-center justify-center',
          canSend ? 'bg-primary' : 'bg-surface-raised',
        )}
      >
        <Ionicons name="arrow-up" size={20} color={canSend ? palette.primaryInk : palette.textTertiary} />
      </Pressable>
    </View>
  );
}
