import { Text, type TextStyle, type StyleProp } from 'react-native';
import { fonts } from '@/constants/theme';

interface WordmarkProps {
  size?: number;
  color: string;
  style?: StyleProp<TextStyle>;
}

/** The AURA wordmark: Playfair, widely spaced capitals. */
export function Wordmark({ size = 20, color, style }: WordmarkProps) {
  return (
    <Text
      accessibilityRole="header"
      accessibilityLabel="AURA"
      style={[
        {
          fontFamily: fonts.displayMedium,
          fontSize: size,
          lineHeight: size * 1.15,
          letterSpacing: size * 0.32,
          color,
          paddingLeft: size * 0.32,
        },
        style,
      ]}
    >
      AURA
    </Text>
  );
}
