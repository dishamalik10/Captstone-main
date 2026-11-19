import type { ClothingCategory, Occasion, StylePreference } from '@/types';

export const CLOTHING_CATEGORIES: { key: ClothingCategory | 'all'; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'tops', label: 'Tops' },
  { key: 'bottoms', label: 'Bottoms' },
  { key: 'dresses', label: 'Dresses' },
  { key: 'shoes', label: 'Shoes' },
  { key: 'outerwear', label: 'Outerwear' },
  { key: 'accessories', label: 'Accessories' },
];

export const MARKETPLACE_CATEGORIES: { key: ClothingCategory | 'all' | 'trending'; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'tops', label: 'Tops' },
  { key: 'bottoms', label: 'Bottoms' },
  { key: 'shoes', label: 'Shoes' },
  { key: 'accessories', label: 'Accessories' },
  { key: 'trending', label: 'Trending' },
];

export const OCCASIONS: { key: Occasion; label: string; icon: string }[] = [
  { key: 'date', label: 'Date', icon: 'heart-outline' },
  { key: 'party', label: 'Party', icon: 'wine-outline' },
  { key: 'meeting', label: 'Meeting', icon: 'briefcase-outline' },
  { key: 'casual', label: 'Casual', icon: 'sunny-outline' },
  { key: 'wedding', label: 'Wedding', icon: 'diamond-outline' },
  { key: 'interview', label: 'Interview', icon: 'document-text-outline' },
  { key: 'travel', label: 'Travel', icon: 'airplane-outline' },
];

export const STYLE_PREFERENCES: { key: StylePreference; label: string }[] = [
  { key: 'minimalist', label: 'Minimalist' },
  { key: 'streetwear', label: 'Streetwear' },
  { key: 'formal', label: 'Formal' },
  { key: 'bohemian', label: 'Bohemian' },
  { key: 'athleisure', label: 'Athleisure' },
  { key: 'vintage', label: 'Vintage' },
  { key: 'smart_casual', label: 'Smart Casual' },
  { key: 'edgy', label: 'Edgy' },
];

export const BODY_SHAPES = [
  { key: 'hourglass' as const, label: 'Hourglass' },
  { key: 'rectangle' as const, label: 'Rectangle' },
  { key: 'pear' as const, label: 'Pear' },
  { key: 'apple' as const, label: 'Apple' },
  { key: 'athletic' as const, label: 'Athletic' },
];

export const SKIN_TONES = [
  { key: 'fair' as const, color: '#F5D0B5', label: 'Fair' },
  { key: 'light' as const, color: '#E8B89A', label: 'Light' },
  { key: 'medium' as const, color: '#C68642', label: 'Medium' },
  { key: 'olive' as const, color: '#A67B5B', label: 'Olive' },
  { key: 'tan' as const, color: '#8D5524', label: 'Tan' },
  { key: 'deep' as const, color: '#4A2912', label: 'Deep' },
];

export const SIZES = ['XS', 'S', 'M', 'L', 'XL', 'XXL'] as const;

export const SEASONS = ['spring', 'summer', 'fall', 'winter', 'all'] as const;

export const COLORS_FILTER = [
  'Black', 'White', 'Navy', 'Beige', 'Red', 'Green', 'Blue', 'Brown', 'Grey', 'Gold',
];
