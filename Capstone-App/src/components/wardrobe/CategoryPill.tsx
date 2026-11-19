import { ScrollView } from 'react-native';
import { Chip } from '@/components/ui/Chip';
import { CLOTHING_CATEGORIES } from '@/constants/categories';
import type { ClothingCategory } from '@/types';

interface CategoryPillProps {
  selected: ClothingCategory | 'all';
  onSelect: (category: ClothingCategory | 'all') => void;
}

export function CategoryPill({ selected, onSelect }: CategoryPillProps) {
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      style={{ flexGrow: 0, flexShrink: 0 }}
      contentContainerStyle={{ paddingHorizontal: 16, paddingVertical: 8 }}
    >
      {CLOTHING_CATEGORIES.map((cat) => (
        <Chip
          key={cat.key}
          label={cat.label}
          selected={selected === cat.key}
          onPress={() => onSelect(cat.key)}
          className="mb-0"
        />
      ))}
    </ScrollView>
  );
}
