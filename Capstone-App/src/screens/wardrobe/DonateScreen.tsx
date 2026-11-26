import { useEffect, useMemo, useState } from 'react';
import { View, Text, ScrollView, Pressable } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { ScreenWrapper } from '@/components/shared/ScreenWrapper';
import { Header } from '@/components/shared/Header';
import { EmptyState } from '@/components/shared/EmptyState';
import { AppImage } from '@/components/shared/AppImage';
import { Button } from '@/components/ui/Button';
import { Chip } from '@/components/ui/Chip';
import { Modal } from '@/components/ui/Modal';
import { useToastStore } from '@/components/ui/Toast';
import { useDonateItems, useDonationCandidates } from '@/hooks';
import { useThemeColors } from '@/hooks/useThemeColors';
import { donationService } from '@/services';
import { useWardrobeStore } from '@/store/wardrobeStore';
import { layout } from '@/constants/theme';
import { cn } from '@/utils/helpers';
import { saveTextFile } from '@/utils/download';
import type { DonationCandidate } from '@/types';

const AGE_FILTERS = [
  { days: 0, label: 'Never worn' },
  { days: 30, label: 'Owned 30+ days' },
  { days: 90, label: 'Owned 90+ days' },
  { days: 180, label: 'Owned 6+ months' },
];

function ownedFor(days: number) {
  if (days === 0) return 'Added today';
  if (days < 60) return `Owned ${days} ${days === 1 ? 'day' : 'days'}`;
  return `Owned ${Math.round(days / 30)} months`;
}

export function DonateScreen() {
  const navigation = useNavigation();
  const palette = useThemeColors();
  const showToast = useToastStore((s) => s.show);
  const removeFromWardrobe = useWardrobeStore((s) => s.removeItem);
  const [minDays, setMinDays] = useState(0);
  const { data: items, isLoading, isError, refetch } = useDonationCandidates(minDays);
  const donate = useDonateItems();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [downloading, setDownloading] = useState(false);
  const [confirming, setConfirming] = useState(false);

  // Drop selections that are no longer in the list (filter changed or items donated).
  useEffect(() => {
    if (!items) return;
    const visible = new Set(items.map((item) => item.id));
    setSelected((current) => new Set([...current].filter((id) => visible.has(id))));
  }, [items]);

  const list = items ?? [];
  const allSelected = list.length > 0 && selected.size === list.length;
  const selectedItems = useMemo(() => list.filter((item) => selected.has(item.id)), [list, selected]);

  const toggle = (id: string) => setSelected((current) => {
    const next = new Set(current);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  });

  const download = async () => {
    setDownloading(true);
    try {
      const csv = await donationService.getCandidatesCsv(minDays);
      const date = new Date().toISOString().slice(0, 10);
      await saveTextFile(`aura-unworn-clothes-${date}.csv`, csv);
      showToast('Unworn clothes list ready', 'success');
    } catch {
      showToast('Could not download the list', 'error');
    } finally {
      setDownloading(false);
    }
  };

  const confirmDonate = async () => {
    setConfirming(false);
    try {
      const donated = await donate.mutateAsync([...selected]);
      donated.forEach(removeFromWardrobe);
      setSelected(new Set());
      showToast(`${donated.length} ${donated.length === 1 ? 'piece' : 'pieces'} marked as donated`, 'success');
    } catch {
      showToast('Could not mark items as donated', 'error');
    }
  };

  return (
    <ScreenWrapper error={isError ? 'Could not load your unworn clothes.' : null} onRetry={refetch}>
      <Header
        title="Donate unworn clothes"
        subtitle="Pieces you have never marked as worn"
        showBack
        onBack={() => navigation.goBack()}
      />
      <ScrollView contentContainerStyle={{ paddingHorizontal: 20, paddingBottom: 140 }} showsVerticalScrollIndicator={false}>
        <View className="w-full self-center" style={{ maxWidth: layout.reading }}>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            style={{ flexGrow: 0 }}
            contentContainerStyle={{ paddingVertical: 12 }}
            accessibilityRole="radiogroup"
          >
            {AGE_FILTERS.map((filter) => (
              <Chip
                key={filter.days}
                label={filter.label}
                selected={minDays === filter.days}
                onPress={() => setMinDays(filter.days)}
              />
            ))}
          </ScrollView>

          {isLoading ? null : !list.length ? (
            <View className="min-h-[420px]">
              <EmptyState
                icon="heart-outline"
                title="Nothing to donate"
                message={minDays
                  ? 'Every piece you have owned this long has been worn. Try a shorter time.'
                  : 'You have worn every piece in your wardrobe at least once.'}
              />
            </View>
          ) : (
            <>
              <View className="flex-row items-end justify-between pt-2 pb-4 border-b border-text-primary">
                <View className="flex-1 pr-3">
                  <Text className="text-text-primary font-display text-3xl tabular-nums">{list.length}</Text>
                  <Text className="text-text-secondary font-body text-sm">
                    {list.length === 1 ? 'piece never worn' : 'pieces never worn'}
                  </Text>
                </View>
                <Button
                  variant="secondary"
                  size="sm"
                  icon="download-outline"
                  label={downloading ? 'Preparing…' : 'Download list'}
                  loading={downloading}
                  onPress={() => void download()}
                />
              </View>

              <Pressable
                onPress={() => setSelected(allSelected ? new Set() : new Set(list.map((item) => item.id)))}
                accessibilityRole="button"
                className="py-3 self-start"
              >
                <Text className="text-accent font-body-medium text-sm">
                  {allSelected ? 'Clear selection' : 'Select all'}
                </Text>
              </Pressable>

              {list.map((item) => (
                <CandidateRow
                  key={item.id}
                  item={item}
                  selected={selected.has(item.id)}
                  onToggle={() => toggle(item.id)}
                  checkColor={palette.primaryInk}
                />
              ))}

              <Text className="text-text-tertiary font-body text-xs mt-4">
                “Worn” means part of an outfit you marked as worn in AURA. Pieces you wore without marking them still show here.
              </Text>
            </>
          )}
        </View>
      </ScrollView>

      {selected.size > 0 && (
        <View className="absolute left-0 right-0 bottom-0 px-5 pb-8 pt-3 bg-background border-t border-border">
          <View className="w-full self-center" style={{ maxWidth: layout.reading }}>
            <Button
              icon="heart-outline"
              label={`Mark ${selected.size} as donated`}
              loading={donate.isPending}
              onPress={() => setConfirming(true)}
            />
          </View>
        </View>
      )}

      <Modal
        visible={confirming}
        onClose={() => setConfirming(false)}
        title={`Donate ${selected.size} ${selected.size === 1 ? 'piece' : 'pieces'}?`}
        message={`${selectedItems.slice(0, 3).map((item) => item.name).join(', ')}${selectedItems.length > 3 ? ` and ${selectedItems.length - 3} more` : ''} will leave your wardrobe and stop appearing in outfit suggestions.`}
        confirmLabel="Mark as donated"
        onConfirm={() => void confirmDonate()}
      />
    </ScreenWrapper>
  );
}

function CandidateRow({
  item,
  selected,
  onToggle,
  checkColor,
}: {
  item: DonationCandidate;
  selected: boolean;
  onToggle: () => void;
  checkColor: string;
}) {
  return (
    <Pressable
      onPress={onToggle}
      accessibilityRole="checkbox"
      accessibilityState={{ checked: selected }}
      accessibilityLabel={`${item.name}, ${item.color}, ${ownedFor(item.daysInWardrobe)}`}
      className="flex-row items-center gap-4 py-3 border-b border-border"
    >
      <AppImage source={{ uri: item.imageUrl }} className="w-16 h-20 rounded-sm" contentFit="cover" />
      <View className="flex-1">
        <Text className="text-text-primary font-body-medium text-base" numberOfLines={1}>{item.name}</Text>
        <Text className="text-text-secondary font-body text-sm" numberOfLines={1}>
          {item.color} · {item.season === 'all' ? 'All-season' : item.season.charAt(0).toUpperCase() + item.season.slice(1)}
        </Text>
        <Text className="text-text-tertiary font-body text-xs mt-0.5 tabular-nums">{ownedFor(item.daysInWardrobe)}</Text>
      </View>
      <View
        className={cn(
          'w-6 h-6 rounded-full border items-center justify-center',
          selected ? 'bg-primary border-primary' : 'border-border',
        )}
      >
        {selected && <Ionicons name="checkmark" size={15} color={checkColor} />}
      </View>
    </Pressable>
  );
}
