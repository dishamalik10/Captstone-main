/**
 * AURA design tokens: the single source of truth.
 *
 * Tailwind classes (bg-background, text-accent, ...) resolve to CSS variables
 * whose values come from `palettes` below. On native they are applied with
 * NativeWind `vars()` at the app root; on web they are written to :root.
 * Anything that needs a raw colour (icons, switches, SVG) reads the same
 * palette through `useThemeColors()`.
 */
import { vars } from 'nativewind';

export type ThemeName = 'dark' | 'light';

export interface Palette {
  background: string;
  surface: string;
  surfaceRaised: string;
  border: string;
  borderStrong: string;
  textPrimary: string;
  textSecondary: string;
  textTertiary: string;
  accent: string;
  accentInk: string;
  accentSoft: string;
  /** Filled primary actions and selections: ink on ivory, ivory on night. */
  primary: string;
  primaryInk: string;
  /** The stylist's colour: terracotta, used only where AURA speaks. */
  stylist: string;
  stylistInk: string;
  stylistMuted: string;
  destructive: string;
  success: string;
  warning: string;
  scrim: string;
}

/** Night: the landing page's technology band, warm charcoal with ivory ink and a lighter clay signal. */
const dark: Palette = {
  background: '#1D1A16',
  surface: '#24201B',
  surfaceRaised: '#2A2621',
  border: '#3A352E',
  borderStrong: '#57503F',
  textPrimary: '#F4EFE6',
  textSecondary: '#B3AA9C',
  textTertiary: '#958C7E',
  accent: '#D98A6C',
  accentInk: '#1D1A16',
  accentSoft: '#3A2820',
  primary: '#F4EFE6',
  primaryInk: '#1D1A16',
  stylist: '#D98A6C',
  stylistInk: '#1D1A16',
  stylistMuted: '#4A2418',
  destructive: '#E5857A',
  success: '#86C9A3',
  warning: '#DDAE68',
  scrim: '#000000',
};

/** Paper: the landing page itself. Ivory, deep charcoal ink, one terracotta signal that holds 5.3:1. */
const light: Palette = {
  background: '#F4EFE6',
  surface: '#FBF8F2',
  surfaceRaised: '#ECE5D8',
  border: '#D6CCBB',
  borderStrong: '#B3A794',
  textPrimary: '#1D1A16',
  textSecondary: '#463F37',
  textTertiary: '#6E665B',
  accent: '#A0482E',
  accentInk: '#FBF3EC',
  accentSoft: '#EEDDD1',
  primary: '#1D1A16',
  primaryInk: '#F4EFE6',
  stylist: '#A0482E',
  stylistInk: '#FBF3EC',
  stylistMuted: '#F7E1D3',
  destructive: '#A63D2C',
  success: '#2F7A52',
  warning: '#8F5D14',
  scrim: '#1D1A16',
};

export const palettes: Record<ThemeName, Palette> = { dark, light };

/**
 * The landing page is always set on ivory paper. Its tokens are the app's own
 * palettes, so the marketing page and the product share one material.
 */
export const landing = {
  paper: light.background,
  paper2: light.surfaceRaised,
  paper3: '#E3DACA',
  card: light.surface,
  ink: light.textPrimary,
  ink2: light.textSecondary,
  muted: light.textTertiary,
  rule: light.border,
  gold: light.accent,
  goldOnInk: dark.accent,
  terracotta: light.stylist,
  terracottaInk: light.stylistInk,
  terracottaMuted: light.stylistMuted,
  inkPaper: light.background,
  night: dark.background,
  night2: dark.surfaceRaised,
  nightMuted: dark.textSecondary,
  nightRule: dark.border,
} as const;

/** Legacy export: the dark palette, kept for existing imports. */
export const colors = {
  ...dark,
} as const;

export const fonts = {
  display: 'PlayfairDisplay_400Regular',
  displayMedium: 'PlayfairDisplay_500Medium',
  displayBold: 'PlayfairDisplay_700Bold',
  body: 'Inter_400Regular',
  bodyMedium: 'Inter_500Medium',
  bodySemibold: 'Inter_600SemiBold',
} as const;

export const spacing = {
  1: 4,
  2: 8,
  3: 12,
  4: 16,
  5: 20,
  6: 24,
  8: 32,
  10: 40,
  12: 48,
  16: 64,
} as const;

export const radius = {
  sm: 4,
  md: 8,
  lg: 14,
  xl: 20,
  full: 9999,
} as const;

export const motion = {
  micro: 120,
  short: 220,
  long: 420,
} as const;

/** Content widths so wide screens grow gutters, not measures. */
export const layout = {
  content: 1120,
  app: 1280,
  form: 440,
  reading: 640,
} as const;

function triplet(hex: string): string {
  const h = hex.replace('#', '');
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `${r} ${g} ${b}`;
}

const VAR_NAMES: Record<keyof Palette, string> = {
  background: '--color-background',
  surface: '--color-surface',
  surfaceRaised: '--color-surface-raised',
  border: '--color-border',
  borderStrong: '--color-border-strong',
  textPrimary: '--color-text-primary',
  textSecondary: '--color-text-secondary',
  textTertiary: '--color-text-tertiary',
  accent: '--color-accent',
  accentInk: '--color-accent-ink',
  accentSoft: '--color-accent-soft',
  primary: '--color-primary',
  primaryInk: '--color-primary-ink',
  stylist: '--color-stylist',
  stylistInk: '--color-stylist-ink',
  stylistMuted: '--color-stylist-muted',
  destructive: '--color-destructive',
  success: '--color-success',
  warning: '--color-warning',
  scrim: '--color-scrim',
};

/** CSS variable map (name → "r g b") for a palette. */
export function cssVariables(name: ThemeName): Record<string, string> {
  const palette = palettes[name];
  const out: Record<string, string> = {};
  (Object.keys(VAR_NAMES) as (keyof Palette)[]).forEach((key) => {
    out[VAR_NAMES[key]] = triplet(palette[key]);
  });
  return out;
}

/** NativeWind style objects that set the variables for a subtree. */
export const themeVars = {
  dark: vars(cssVariables('dark')),
  light: vars(cssVariables('light')),
};

/** Hex colour with an alpha, for overlays and shadows only. */
export function withAlpha(hex: string, alpha: number): string {
  const a = Math.round(Math.max(0, Math.min(1, alpha)) * 255)
    .toString(16)
    .padStart(2, '0');
  return `${hex.slice(0, 7)}${a}`;
}
