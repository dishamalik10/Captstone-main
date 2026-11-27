import { useEffect, useState } from 'react';
import { Text, View } from 'react-native';
import { Button } from '@/components/ui/Button';
import { Chip } from '@/components/ui/Chip';
import { Input } from '@/components/ui/Input';
import type { ClothingCategory, GarmentMeasurements, GarmentSize } from '@/types';

type Field = keyof GarmentMeasurements;

const FIELDS: Record<'top' | 'bottom' | 'dress', [Field, string][]> = {
  top: [['chest_flat_cm', 'Chest, flat (cm)'], ['waist_flat_cm', 'Waist, flat (cm)'], ['length_cm', 'Length (cm)']],
  dress: [['chest_flat_cm', 'Chest, flat (cm)'], ['waist_flat_cm', 'Waist, flat (cm)'], ['hip_flat_cm', 'Hip, flat (cm)'], ['length_cm', 'Length (cm)']],
  bottom: [['waist_flat_cm', 'Waist, flat (cm)'], ['hip_flat_cm', 'Hip, flat (cm)'], ['inseam_cm', 'Inseam (cm)']],
};
const CHARTS: { key: NonNullable<GarmentSize['chart']>; label: string }[] = [
  { key: 'women', label: "Women's" }, { key: 'men', label: "Men's" }, { key: 'unisex', label: 'Not sure' },
];

function group(category: ClothingCategory): 'top' | 'bottom' | 'dress' | null {
  if (category === 'tops' || category === 'outerwear') return 'top';
  if (category === 'bottoms') return 'bottom';
  if (category === 'dresses') return 'dress';
  return null;
}

/** Size label, size chart and optional flat measurements of a garment (ENGINEERING_PLAN 4.11). */
export function SizeEditor({ category, size, saving, onSave }: {
  category: ClothingCategory;
  size: GarmentSize | null | undefined;
  saving: boolean;
  onSave: (size: GarmentSize | null) => void;
}) {
  const [label, setLabel] = useState(size?.label ?? '');
  const [chart, setChart] = useState<GarmentSize['chart']>(size?.chart ?? 'unisex');
  const [values, setValues] = useState<Record<string, string>>({});
  const [showMeasurements, setShowMeasurements] = useState(Boolean(size?.measurements && Object.keys(size.measurements).length));

  useEffect(() => {
    setLabel(size?.label ?? '');
    setChart(size?.chart ?? 'unisex');
    const measured = size?.measurements ?? {};
    setValues(Object.fromEntries(Object.entries(measured).map(([k, v]) => [k, v == null ? '' : String(v)])));
  }, [size]);

  const fields = group(category);
  if (!fields) return null;

  const save = () => {
    const measurements: GarmentMeasurements = {};
    for (const [field] of FIELDS[fields]) {
      const number = Number((values[field] ?? '').replace(',', '.'));
      if (values[field]?.trim() && Number.isFinite(number) && number > 0) measurements[field] = number;
    }
    const empty = !label.trim() && Object.keys(measurements).length === 0;
    onSave(empty ? null : { label: label.trim() || null, chart, measurements });
  };

  return (
    <View className="mt-10">
      <Text className="text-text-primary font-display text-xl mb-1">Size</Text>
      <Text className="text-text-secondary font-body text-sm mb-3">
        Add the size on the label for size advice and a truer try-on. Measurements laid flat are even better.
      </Text>
      <Input label="Size label" value={label} onChangeText={setLabel} maxLength={20} autoCapitalize="characters"
        hint="For example M, UK 12, EU 50 or 32/32" />
      <View className="flex-row flex-wrap mt-2">
        {CHARTS.map((option) => (
          <Chip key={option.key} label={option.label} selected={chart === option.key} onPress={() => setChart(option.key)} />
        ))}
      </View>
      {showMeasurements ? (
        <View className="mt-2">
          {FIELDS[fields].map(([field, fieldLabel]) => (
            <Input key={field} label={fieldLabel} value={values[field] ?? ''} keyboardType="decimal-pad" maxLength={6}
              onChangeText={(text) => setValues((current) => ({ ...current, [field]: text }))} containerClassName="mt-2" />
          ))}
        </View>
      ) : (
        <View className="mt-2 self-start">
          <Button variant="ghost" icon="resize-outline" label="Add garment measurements" onPress={() => setShowMeasurements(true)} />
        </View>
      )}
      <View className="mt-3">
        <Button variant="secondary" label="Save size" loading={saving} onPress={save} />
      </View>
    </View>
  );
}
