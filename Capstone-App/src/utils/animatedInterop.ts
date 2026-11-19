/**
 * NativeWind only maps `className` to `style` on components it knows about.
 * Reanimated's animated components are created outside it, so register them
 * once here (imported first by App.tsx) and every `className` on them works.
 */
import { Pressable } from 'react-native';
import Animated from 'react-native-reanimated';
import { cssInterop } from 'nativewind';
import { SafeAreaView } from 'react-native-safe-area-context';

export const AnimatedPressable = Animated.createAnimatedComponent(Pressable);

cssInterop(Animated.View, { className: 'style' });
cssInterop(Animated.Text, { className: 'style' });
cssInterop(Animated.ScrollView, { className: 'style', contentContainerClassName: 'contentContainerStyle' });
cssInterop(AnimatedPressable, { className: 'style' });
cssInterop(SafeAreaView, { className: 'style' });
