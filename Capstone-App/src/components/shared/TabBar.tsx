import { useEffect, useState } from 'react';
import { View, Pressable, Text, Keyboard } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withTiming, Easing } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import type { BottomTabBarProps } from '@react-navigation/bottom-tabs';
import { hapticLight } from '@/utils/haptics';
import { cn } from '@/utils/helpers';
import { useThemeColors } from '@/hooks/useThemeColors';
import { layout, motion } from '@/constants/theme';

const TABS = [
  { name: 'Home', label: 'Home', icon: 'home-outline', activeIcon: 'home' },
  { name: 'Wardrobe', label: 'Wardrobe', icon: 'shirt-outline', activeIcon: 'shirt' },
  { name: 'AIStylist', label: 'Stylist', icon: 'sparkles-outline', activeIcon: 'sparkles' },
  { name: 'AIChat', label: 'Chat', icon: 'chatbubble-ellipses-outline', activeIcon: 'chatbubble-ellipses' },
  { name: 'Profile', label: 'Profile', icon: 'person-outline', activeIcon: 'person' },
] as const;

export function TabBar({ state, navigation }: BottomTabBarProps) {
  const insets = useSafeAreaInsets();
  const palette = useThemeColors();
  const [keyboardVisible, setKeyboardVisible] = useState(false);

  useEffect(() => {
    const showSub = Keyboard.addListener('keyboardDidShow', () => setKeyboardVisible(true));
    const hideSub = Keyboard.addListener('keyboardDidHide', () => setKeyboardVisible(false));
    return () => {
      showSub.remove();
      hideSub.remove();
    };
  }, []);

  if (keyboardVisible) return null;

  return (
    <View
      accessibilityRole="tablist"
      style={{
        paddingBottom: Math.max(insets.bottom, 8),
        width: '100%',
        maxWidth: layout.app,
        alignSelf: 'center',
        backgroundColor: palette.background,
      }}
      className="absolute bottom-0 border-t border-border"
    >
      <View className="flex-row items-stretch justify-around px-2">
        {state.routes.map((route, index) => {
          const tab = TABS.find((t) => t.name === route.name) ?? TABS[0];
          const isFocused = state.index === index;

          return (
            <TabItem
              key={route.key}
              label={tab.label}
              icon={tab.icon}
              activeIcon={tab.activeIcon}
              focused={isFocused}
              onPress={() => {
                hapticLight();
                const event = navigation.emit({ type: 'tabPress', target: route.key, canPreventDefault: true });
                if (!isFocused && !event.defaultPrevented) navigation.navigate(route.name);
              }}
            />
          );
        })}
      </View>
    </View>
  );
}

function TabItem({
  label,
  icon,
  activeIcon,
  focused,
  onPress,
}: {
  label: string;
  icon: string;
  activeIcon: string;
  focused: boolean;
  onPress: () => void;
}) {
  const palette = useThemeColors();
  const progress = useSharedValue(focused ? 1 : 0);

  useEffect(() => {
    progress.value = withTiming(focused ? 1 : 0, { duration: motion.short, easing: Easing.out(Easing.cubic) });
  }, [focused, progress]);

  const indicatorStyle = useAnimatedStyle(() => ({
    opacity: progress.value,
    transform: [{ scaleX: 0.3 + 0.7 * progress.value }],
  }));
  const iconStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: -1.5 * progress.value }],
  }));

  return (
    <Pressable
      accessibilityRole="tab"
      accessibilityState={{ selected: focused }}
      accessibilityLabel={label}
      onPress={onPress}
      className="flex-1 items-center pt-2.5 pb-1.5 min-h-14"
    >
      <Animated.View style={indicatorStyle} className="absolute top-0 h-0.5 w-7 rounded-full bg-accent" />
      <Animated.View style={iconStyle}>
        <Ionicons
          name={(focused ? activeIcon : icon) as keyof typeof Ionicons.glyphMap}
          size={22}
          color={focused ? palette.accent : palette.textTertiary}
        />
      </Animated.View>
      <Text
        numberOfLines={1}
        className={cn(
          'text-[11px] leading-4 mt-1',
          focused ? 'text-text-primary font-body-medium' : 'text-text-tertiary font-body',
        )}
      >
        {label}
      </Text>
    </Pressable>
  );
}
