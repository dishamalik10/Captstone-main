import { Text, View, type StyleProp, type ViewStyle } from 'react-native';
import { fonts, palettes, type ThemeName } from '@/constants/theme';
import { useResolvedTheme } from '@/hooks/useThemeColors';

interface StylistNoteProps {
  text: string;
  title?: string;
  /** Force a theme (the landing page is always 'light'); defaults to the app's resolved theme. */
  theme?: ThemeName;
  style?: StyleProp<ViewStyle>;
}

/**
 * The stylist's voice, shared by the landing page and the app: an inverse note
 * in terracotta, the stylist's colour, with the AURA monogram.
 */
export function StylistNote({ text, title = 'Why this works', theme, style }: StylistNoteProps) {
  const resolved = useResolvedTheme();
  const scheme = theme ?? resolved;
  const p = palettes[scheme];
  return (
    <View
      accessibilityLabel={`${title}. ${text}`}
      style={[
        {
          backgroundColor: p.stylist,
          borderRadius: 10,
          borderBottomLeftRadius: 2,
          paddingHorizontal: 16,
          paddingVertical: 14,
        },
        style,
      ]}
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <View
          style={{
            width: 20,
            height: 20,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: p.stylistMuted,
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Text style={{ fontFamily: fonts.display, fontSize: 11, color: p.stylistMuted }}>A</Text>
        </View>
        <Text style={{ fontFamily: fonts.bodyMedium, fontSize: 13, color: p.stylistMuted }}>{title}</Text>
      </View>
      <Text style={{ fontFamily: fonts.body, fontSize: 15, lineHeight: 22, color: p.stylistInk }}>{text}</Text>
    </View>
  );
}
