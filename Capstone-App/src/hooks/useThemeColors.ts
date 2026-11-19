import { useColorScheme } from 'react-native';
import { palettes, type Palette, type ThemeName } from '@/constants/theme';
import { useAppearanceStore } from '@/store/appearanceStore';

/** The resolved appearance ('dark' | 'light') after applying the user's choice. */
export function useResolvedTheme(): ThemeName {
  const systemScheme = useColorScheme();
  const mode = useAppearanceStore((state) => state.mode);
  if (mode === 'system') return systemScheme === 'light' ? 'light' : 'dark';
  return mode;
}

/** Raw palette colours for props that cannot take a className (icons, switches, SVG). */
export function useThemeColors(): Palette & { scheme: ThemeName } {
  const scheme = useResolvedTheme();
  return { ...palettes[scheme], scheme };
}
