import { Modal as RNModal, View, Text, Pressable, StyleSheet } from 'react-native';
import Animated, { FadeIn, FadeOut, FadeInDown } from 'react-native-reanimated';
import { BlurView } from 'expo-blur';
import { Ionicons } from '@expo/vector-icons';
import { Button } from './Button';
import { hapticLight } from '@/utils/haptics';
import { useThemeColors } from '@/hooks/useThemeColors';
import { motion, withAlpha } from '@/constants/theme';

interface ModalProps {
  visible: boolean;
  onClose: () => void;
  title: string;
  message?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm?: () => void;
  destructive?: boolean;
}

export function Modal({
  visible,
  onClose,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  onConfirm,
  destructive,
}: ModalProps) {
  const palette = useThemeColors();
  return (
    <RNModal visible={visible} transparent animationType="none" onRequestClose={onClose} statusBarTranslucent>
      <Animated.View
        entering={FadeIn.duration(motion.short)}
        exiting={FadeOut.duration(motion.micro)}
        style={StyleSheet.absoluteFill}
        className="justify-center px-6"
      >
        <BlurView
          intensity={24}
          tint={palette.scheme === 'dark' ? 'dark' : 'light'}
          style={StyleSheet.absoluteFill}
        />
        <Pressable
          accessibilityLabel="Dismiss"
          onPress={onClose}
          style={[StyleSheet.absoluteFill, { backgroundColor: withAlpha(palette.scrim, palette.scheme === 'dark' ? 0.55 : 0.28) }]}
        />
        <Animated.View
          entering={FadeInDown.duration(motion.long)}
          accessibilityViewIsModal
          className="bg-surface rounded-lg border border-border p-6 w-full max-w-md self-center"
        >
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Close"
            onPress={() => {
              hapticLight();
              onClose();
            }}
            className="absolute right-2 top-2 z-10 w-11 h-11 items-center justify-center rounded-full hover:bg-surface-raised"
          >
            <Ionicons name="close" size={22} color={palette.textSecondary} />
          </Pressable>
          <Text accessibilityRole="header" className="text-text-primary font-display text-2xl mb-2 pr-10">
            {title}
          </Text>
          {message && <Text className="text-text-secondary font-body text-base mb-6">{message}</Text>}
          <View className="flex-row gap-3">
            <View className="flex-1">
              <Button variant="secondary" label={cancelLabel} onPress={onClose} />
            </View>
            {onConfirm && (
              <View className="flex-1">
                <Button
                  variant={destructive ? 'destructive' : 'primary'}
                  label={confirmLabel}
                  onPress={() => {
                    onConfirm();
                    onClose();
                  }}
                />
              </View>
            )}
          </View>
        </Animated.View>
      </Animated.View>
    </RNModal>
  );
}
