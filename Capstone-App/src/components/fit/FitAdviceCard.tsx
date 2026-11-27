import { ActivityIndicator, Text, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { useThemeColors } from '@/hooks/useThemeColors';
import type { FitAdvice, FitRating } from '@/types';
import { cn } from '@/utils/helpers';

const ZONE_LABEL: Record<string, string> = { chest: 'Chest', waist: 'Waist', hip: 'Hip', inseam: 'Leg length', length: 'Length' };
const RATING_LABEL: Record<string, string> = {
  tight: 'Tight', snug: 'Snug', regular: 'Regular', relaxed: 'Relaxed', loose: 'Loose',
  short: 'Short', long: 'Long', cropped: 'Cropped',
};
const RATING_TONE: Record<FitRating, string> = {
  tight: 'border-destructive', snug: 'border-warning', regular: 'border-success', relaxed: 'border-border-strong', loose: 'border-warning',
};

interface FitAdviceCardProps {
  /** React Query key; include everything the advice depends on (item size, measurements). */
  queryKey: readonly unknown[];
  load: () => Promise<FitAdvice>;
  title?: string;
  /** Compact: one line ("Shirt: Should fit well"), for lists such as the try-on outfit pieces; nothing when there is no advice. */
  compact?: boolean;
  /** The piece's name, shown before the verdict in compact mode. */
  label?: string;
}

/**
 * Size advice for the signed-in user (ENGINEERING_PLAN 4.11): a verdict and a rating per
 * body zone. Display only; it never changes recommendations. Marked "estimated" whenever
 * it relies on photo estimates, a generic size chart or the user's usual size.
 */
export function FitAdviceCard({ queryKey, load, title = 'How it should fit you', compact = false, label }: FitAdviceCardProps) {
  const palette = useThemeColors();
  const { data, isLoading, isError } = useQuery({ queryKey: ['fit', ...queryKey], queryFn: load, staleTime: 60_000 });

  if (isLoading) {
    return compact ? null : (
      <View className="mt-6 flex-row items-center gap-2">
        <ActivityIndicator color={palette.accent} />
        <Text className="text-text-secondary font-body text-sm">Checking the fit…</Text>
      </View>
    );
  }
  if (isError || !data) return null;
  if (compact) {
    if (!data.available) return null;
    return (
      <Text className="text-text-secondary font-body text-xs">
        {label ? `${label}: ` : ''}{data.verdict}{data.estimated ? ' (estimated)' : ''}
      </Text>
    );
  }
  return (
    <View className="mt-8 rounded-md border border-border bg-surface p-4" accessibilityLabel={title}>
      <Text accessibilityRole="header" className="text-text-primary font-display text-xl">{title}</Text>
      {!data.available ? (
        <Text className="text-text-secondary font-body text-sm mt-2 leading-5">{data.reason}</Text>
      ) : (
        <>
          <View className="flex-row items-center gap-2 mt-2">
            <Text className="text-text-primary font-body-semibold text-base">{data.verdict}</Text>
            {data.estimated && (
              <View className="px-2 py-0.5 rounded-full border border-border">
                <Text className="text-text-tertiary font-body text-xs">Estimated</Text>
              </View>
            )}
          </View>
          <View className="flex-row flex-wrap gap-2 mt-3">
            {(data.zones ?? []).map((zone) => (
              <View key={zone.zone} className={cn('px-3 py-1.5 rounded-full border', RATING_TONE[zone.rating])}
                accessibilityLabel={`${ZONE_LABEL[zone.zone] ?? zone.zone}: ${RATING_LABEL[zone.rating]}`}>
                <Text className="text-text-primary font-body text-xs">
                  {ZONE_LABEL[zone.zone] ?? zone.zone}: {RATING_LABEL[zone.rating]}
                </Text>
              </View>
            ))}
            {(data.lengths ?? []).map((length) => (
              <View key={length.zone} className="px-3 py-1.5 rounded-full border border-border-strong">
                <Text className="text-text-primary font-body text-xs">
                  {ZONE_LABEL[length.zone] ?? length.zone}: {RATING_LABEL[length.rating] ?? length.rating}
                </Text>
              </View>
            ))}
          </View>
          {(data.notes ?? []).map((note) => (
            <Text key={note} className="text-text-tertiary font-body text-xs mt-2 leading-4">{note}</Text>
          ))}
        </>
      )}
    </View>
  );
}
