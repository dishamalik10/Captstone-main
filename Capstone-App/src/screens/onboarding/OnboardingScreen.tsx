import { useEffect, useRef, useState } from 'react';
import { View, Text, FlatList, Pressable, useWindowDimensions } from 'react-native';
import Animated, { useAnimatedStyle, withTiming, useSharedValue } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Button } from '@/components/ui/Button';
import { AppImage } from '@/components/shared/AppImage';
import { GradientScrim } from '@/components/shared/GradientScrim';
import { hapticLight } from '@/utils/haptics';
import { ONBOARDING_KEY } from '@/constants/storage';
import { useThemeColors } from '@/hooks/useThemeColors';
import { layout, motion } from '@/constants/theme';

const SLIDES = [
  {
    id: '1',
    title: 'Your wardrobe, understood.',
    subtitle: 'Photograph what you own. AURA recognises each piece and keeps it organised.',
    image: 'https://images.unsplash.com/photo-1434389677669-e08b4cac3105?w=1200&h=1500&fit=crop',
    alt: 'Knitwear and boots laid out together',
  },
  {
    id: '2',
    title: 'Outfits for the day ahead.',
    subtitle: 'Choose an occasion. AURA weighs the weather and suggests a look, with its reasons.',
    image: 'https://images.unsplash.com/photo-1496747611176-843222e1e57c?w=1200&h=1500&fit=crop',
    alt: 'A light summer outfit',
  },
  {
    id: '3',
    title: 'A stylist you can ask.',
    subtitle: 'Ask about colours, pairings or tonight’s plan. Answers start from your own clothes.',
    image: 'https://images.unsplash.com/photo-1515372039744-b8f02a3ae446?w=1200&h=1500&fit=crop',
    alt: 'An evening outfit',
  },
];

interface OnboardingScreenProps {
  onComplete: () => void;
  onLogin: () => void;
}

export function OnboardingScreen({ onComplete, onLogin }: OnboardingScreenProps) {
  const [index, setIndex] = useState(0);
  const flatListRef = useRef<FlatList>(null);
  const { width, height } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const palette = useThemeColors();
  const imageHeight = Math.min(height * 0.56, 620);

  const finish = async () => {
    await AsyncStorage.setItem(ONBOARDING_KEY, 'true');
    onComplete();
  };

  const skip = async () => {
    await AsyncStorage.setItem(ONBOARDING_KEY, 'true');
    onLogin();
  };

  return (
    <View className="flex-1 bg-background">
      <View
        className="absolute left-0 right-0 z-10 flex-row items-center justify-between px-5"
        style={{ top: insets.top + 8 }}
      >
        <View className="flex-row gap-1.5 flex-1 max-w-40">
          {SLIDES.map((_, i) => (
            <Segment key={i} active={i <= index} />
          ))}
        </View>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Skip onboarding"
          onPress={() => {
            hapticLight();
            skip();
          }}
          className="min-h-11 px-4 rounded-full items-center justify-center bg-background/70"
        >
          <Text className="text-text-primary font-body-medium text-sm">Skip</Text>
        </Pressable>
      </View>

      <FlatList
        ref={flatListRef}
        data={SLIDES}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        getItemLayout={(_, i) => ({ length: width, offset: width * i, index: i })}
        onMomentumScrollEnd={(e) => {
          setIndex(Math.round(e.nativeEvent.contentOffset.x / width));
        }}
        keyExtractor={(item) => item.id}
        renderItem={({ item, index: i }) => (
          <View style={{ width }} className="flex-1">
            <View style={{ height: imageHeight }} className="w-full overflow-hidden">
              <AppImage source={{ uri: item.image }} className="w-full h-full" contentFit="cover" accessibilityLabel={item.alt} />
              <GradientScrim color={palette.background} opacity={0.6} from={0.75} reverse />
              <GradientScrim color={palette.background} opacity={1} from={0.55} />
            </View>
            <View className="px-6 -mt-10" style={{ maxWidth: layout.form + 48, width: '100%', alignSelf: 'center' }}>
              <Text className="text-accent font-body-medium text-sm mb-3 tabular-nums">
                {String(i + 1).padStart(2, '0')} of {String(SLIDES.length).padStart(2, '0')}
              </Text>
              <Text accessibilityRole="header" className="text-text-primary font-display text-4xl tracking-tight">
                {item.title}
              </Text>
              <Text className="text-text-secondary font-body text-base mt-4">{item.subtitle}</Text>
            </View>
          </View>
        )}
      />

      <View
        className="px-6"
        style={{ paddingBottom: insets.bottom + 24, maxWidth: layout.form + 48, width: '100%', alignSelf: 'center' }}
      >
        {index < SLIDES.length - 1 ? (
          <Button
            label="Next"
            size="lg"
            trailingIcon="arrow-forward"
            onPress={() => {
              flatListRef.current?.scrollToIndex({ index: index + 1 });
              setIndex(index + 1);
            }}
          />
        ) : (
          <Button label="Create my account" size="lg" trailingIcon="arrow-forward" onPress={finish} />
        )}
      </View>
    </View>
  );
}

function Segment({ active }: { active: boolean }) {
  const progress = useSharedValue(active ? 1 : 0);
  useEffect(() => {
    progress.value = withTiming(active ? 1 : 0, { duration: motion.long });
  }, [active, progress]);
  const style = useAnimatedStyle(() => ({ transform: [{ scaleX: progress.value }] }));
  return (
    <View className="flex-1 h-0.5 rounded-full bg-border-strong overflow-hidden">
      <Animated.View style={[style, { transformOrigin: 'left center' }]} className="h-full w-full bg-text-primary" />
    </View>
  );
}
