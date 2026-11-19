import { View, Text, useWindowDimensions } from 'react-native';
import Animated, { FadeIn, FadeInDown } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Button } from '@/components/ui/Button';
import { AppImage } from '@/components/shared/AppImage';
import { GradientScrim } from '@/components/shared/GradientScrim';
import { Wordmark } from '@/components/shared/Wordmark';
import { useThemeColors } from '@/hooks/useThemeColors';
import { layout, motion } from '@/constants/theme';

interface WelcomeScreenProps {
  onGetStarted: () => void;
  onLogin: () => void;
}

const HERO_IMAGE = 'https://images.unsplash.com/photo-1490481651871-ab68de25d43d?w=1200&h=1600&fit=crop';

export function WelcomeScreen({ onGetStarted, onLogin }: WelcomeScreenProps) {
  const palette = useThemeColors();
  const insets = useSafeAreaInsets();
  const { width, height } = useWindowDimensions();
  const wide = width >= 900;

  const copy = (
    <View style={{ width: '100%', maxWidth: layout.form }}>
      <Animated.Text
        entering={FadeInDown.duration(motion.long).delay(80)}
        accessibilityRole="header"
        className="text-text-primary font-display tracking-tight"
        style={{ fontSize: wide ? 56 : 44, lineHeight: wide ? 60 : 48 }}
      >
        Dress from{'\n'}what you own.
      </Animated.Text>
      <Animated.Text
        entering={FadeInDown.duration(motion.long).delay(140)}
        className="text-text-secondary font-body text-base mt-4"
      >
        A personal stylist that turns your wardrobe into outfits for the day ahead.
      </Animated.Text>
      <Animated.View entering={FadeInDown.duration(motion.long).delay(200)} className="mt-8 gap-3">
        <Button label="Get started" size="lg" onPress={onGetStarted} trailingIcon="arrow-forward" />
        <Button variant="ghost" size="lg" label="I already have an account" onPress={onLogin} />
      </Animated.View>
    </View>
  );

  if (wide) {
    return (
      <View className="flex-1 bg-background flex-row">
        <View className="flex-1 overflow-hidden">
          <AppImage source={{ uri: HERO_IMAGE }} className="w-full h-full" contentFit="cover" accessibilityLabel="Folded garments on a rail" />
        </View>
        <View className="flex-1 justify-center px-16" style={{ paddingTop: insets.top }}>
          <Animated.View entering={FadeIn.duration(motion.long)} className="absolute top-10 left-16">
            <Wordmark size={18} color={palette.textPrimary} />
          </Animated.View>
          {copy}
        </View>
      </View>
    );
  }

  return (
    <View className="flex-1 bg-background">
      <View style={{ height: height * 0.56 }} className="w-full overflow-hidden">
        <AppImage source={{ uri: HERO_IMAGE }} className="w-full h-full" contentFit="cover" accessibilityLabel="Folded garments on a rail" />
        <GradientScrim color={palette.background} opacity={0.7} from={0.7} reverse />
        <GradientScrim color={palette.background} opacity={1} from={0.45} />
        <View className="absolute left-0 right-0 items-center" style={{ top: insets.top + 16 }}>
          <Wordmark size={18} color={palette.textPrimary} />
        </View>
      </View>
      <View className="flex-1 px-6 justify-end" style={{ paddingBottom: insets.bottom + 24 }}>
        {copy}
      </View>
    </View>
  );
}
