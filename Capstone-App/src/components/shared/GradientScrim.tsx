import { useId } from 'react';
import { StyleSheet, type StyleProp, type ViewStyle } from 'react-native';
import Svg, { Defs, LinearGradient, Rect, Stop } from 'react-native-svg';

interface GradientScrimProps {
  /** Colour the scrim fades into. */
  color: string;
  /** Opacity at the strong end. */
  opacity?: number;
  /** Where (0 to 1, top to bottom) the fade begins. */
  from?: number;
  /** Fade toward the top instead of the bottom. */
  reverse?: boolean;
  style?: StyleProp<ViewStyle>;
}

/** A vertical fade used under text that sits on photographs. Decorative, ignored by assistive tech. */
export function GradientScrim({ color, opacity = 0.85, from = 0.35, reverse, style }: GradientScrimProps) {
  const id = `scrim-${useId().replace(/:/g, '')}`;
  return (
    <Svg
      pointerEvents="none"
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={[StyleSheet.absoluteFill, style]}
      width="100%"
      height="100%"
      preserveAspectRatio="none"
      viewBox="0 0 1 1"
    >
      <Defs>
        <LinearGradient id={id} x1="0" y1={reverse ? '1' : '0'} x2="0" y2={reverse ? '0' : '1'}>
          <Stop offset={String(from)} stopColor={color} stopOpacity={0} />
          <Stop offset="1" stopColor={color} stopOpacity={opacity} />
        </LinearGradient>
      </Defs>
      <Rect x="0" y="0" width="1" height="1" fill={`url(#${id})`} />
    </Svg>
  );
}
