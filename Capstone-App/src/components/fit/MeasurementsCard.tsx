import { useEffect, useState } from 'react';
import { Alert, Platform, Text, View } from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { Ionicons } from '@expo/vector-icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { useToastStore } from '@/components/ui/Toast';
import { useThemeColors } from '@/hooks/useThemeColors';
import { measurementService } from '@/services';
import { useAuthStore } from '@/store/authStore';
import type { Measurement, MeasurementZone } from '@/types';

const SHOWN: MeasurementZone[] = ['chest', 'waist', 'hip', 'shoulder', 'inseam', 'arm'];
const EDITABLE: MeasurementZone[] = ['chest', 'waist', 'hip', 'inseam'];
const SIDE_TIPS: [keyof typeof Ionicons.glyphMap, string][] = [
  ['swap-horizontal-outline', 'Stand side-on to the camera, full body, head to feet'],
  ['shirt-outline', 'Same fitted clothes as your front photo'],
  ['footsteps-outline', 'Barefoot or flat shoes; stand straight, arms relaxed'],
  ['camera-outline', 'Camera at waist height, about 2.5–3 m away'],
];

function errorDetail(error: unknown, fallback: string): string {
  return (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? fallback;
}

function describe(value: Measurement): string {
  if (value.source === 'you') return `${Math.round(value.value)} cm · measured by you`;
  if (value.range_only && value.low != null && value.high != null) return `roughly ${value.low}–${value.high} cm · estimated`;
  return `${Math.round(value.value)} cm · estimated`;
}

/**
 * Body measurements (ENGINEERING_PLAN 4.11): estimated from the front avatar and a side
 * photo scaled by height, or typed in. Typed values always win. Only the user sees them.
 */
export function MeasurementsCard() {
  const palette = useThemeColors();
  const showToast = useToastStore((s) => s.show);
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ['measurements'], queryFn: () => measurementService.get() });
  const data = query.data;
  const [height, setHeight] = useState('');
  const [editing, setEditing] = useState(false);
  const [typed, setTyped] = useState<Record<string, string>>({});
  const [showGuide, setShowGuide] = useState(false);

  useEffect(() => {
    if (data?.heightCm) setHeight(String(data.heightCm));
  }, [data?.heightCm]);

  const refresh = (updated: Awaited<ReturnType<typeof measurementService.get>>) => {
    queryClient.setQueryData(['measurements'], updated);
    queryClient.invalidateQueries({ queryKey: ['fit'] });
    if (updated.heightCm) useAuthStore.getState().updateProfile({ heightCm: updated.heightCm });
  };

  const heightCm = Number(height);
  const heightValid = Number.isFinite(heightCm) && heightCm >= 120 && heightCm <= 230;

  const estimate = useMutation({
    mutationFn: (asset: ImagePicker.ImagePickerAsset) => measurementService.estimate(
      { uri: asset.uri, fileName: asset.fileName, mimeType: asset.mimeType, file: (asset as { file?: File }).file },
      heightCm,
    ),
    onSuccess: (result) => {
      refresh(result);
      setShowGuide(false);
      if (result.status === 'estimated') showToast('Measurements estimated', 'success');
      else showToast('We could not estimate from these photos. See why below.', 'info');
    },
    onError: (error) => showToast(errorDetail(error, 'Could not measure that photo'), 'error'),
  });

  const save = useMutation({
    mutationFn: () => {
      const values: Partial<Record<MeasurementZone, number | null>> = {};
      for (const zone of EDITABLE) {
        const text = (typed[zone] ?? '').trim();
        if (text === '' && data?.measurements[zone]?.source === 'you') values[zone] = null; // cleared
        else if (text !== '') values[zone] = Number(text.replace(',', '.'));
      }
      return measurementService.update({ ...values, ...(heightValid ? { heightCm } : {}) });
    },
    onSuccess: (updated) => {
      refresh(updated);
      setEditing(false);
      showToast('Measurements saved', 'success');
    },
    onError: (error) => showToast(errorDetail(error, 'Could not save your measurements'), 'error'),
  });

  const pickSide = async (useCamera: boolean) => {
    if (!heightValid) {
      showToast('Enter your height (120–230 cm) first: it sets the scale.', 'error');
      return;
    }
    if (Platform.OS !== 'web') {
      const permission = useCamera
        ? await ImagePicker.requestCameraPermissionsAsync()
        : await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!permission.granted) {
        Alert.alert('Permission needed', useCamera ? 'Allow camera access to take your photo.' : 'Allow photo access to choose your photo.');
        return;
      }
    }
    const launch = useCamera ? ImagePicker.launchCameraAsync : ImagePicker.launchImageLibraryAsync;
    const result = await launch({ mediaTypes: ['images'], quality: 0.9 });
    if (result.canceled) return;
    estimate.mutate(result.assets[0]);
  };

  const startEditing = () => {
    const current: Record<string, string> = {};
    for (const zone of EDITABLE) {
      const value = data?.measurements[zone];
      if (value?.source === 'you') current[zone] = String(value.value);
    }
    setTyped(current);
    setEditing(true);
  };

  if (query.isLoading || !data) return null;
  const last = data.lastEstimate;
  const shown = SHOWN.filter((zone) => data.measurements[zone]);

  return (
    <View className="mt-8 rounded-md border border-border bg-surface p-4">
      <Text accessibilityRole="header" className="text-text-primary font-display text-xl">Body measurements</Text>
      <Text className="text-text-secondary font-body text-sm mt-1 leading-5">
        Used for size advice on your clothes and marketplace listings. Only you can see them.
      </Text>

      <Input label="Height (cm)" value={height} onChangeText={setHeight} keyboardType="number-pad" maxLength={3}
        hint="Required: your height is the scale for every measurement." containerClassName="mt-3" />

      {shown.length > 0 ? (
        <View className="mt-3 border-t border-border">
          {shown.map((zone) => (
            <View key={zone} className="flex-row justify-between py-2.5 border-b border-border">
              <Text className="text-text-secondary font-body text-sm">{data.labels[zone]}</Text>
              <Text className="text-text-primary font-body-medium text-sm tabular-nums">{describe(data.measurements[zone]!)}</Text>
            </View>
          ))}
        </View>
      ) : (
        <Text className="text-text-tertiary font-body text-sm mt-3">No measurements yet.</Text>
      )}

      {last?.status === 'not_estimated' && (
        <View className="mt-3 rounded-sm border border-warning p-3" accessibilityLiveRegion="polite">
          <Text className="text-text-primary font-body-medium text-sm">We didn’t estimate from your last photos</Text>
          {last.problems.map((problem) => (
            <Text key={problem} className="text-text-secondary font-body text-xs mt-1">• {problem}</Text>
          ))}
          <Text className="text-text-secondary font-body text-xs mt-1">Retake the photos, or type your own measurements.</Text>
        </View>
      )}

      {editing ? (
        <View className="mt-3">
          {EDITABLE.map((zone) => (
            <Input key={zone} label={`${data.labels[zone]} (cm)`} value={typed[zone] ?? ''} keyboardType="decimal-pad" maxLength={5}
              onChangeText={(text) => setTyped((current) => ({ ...current, [zone]: text }))} containerClassName="mt-2" />
          ))}
          <Text className="text-text-tertiary font-body text-xs mt-2">Values you type always replace estimates. Clear a field to go back to the estimate.</Text>
          <View className="flex-row gap-3 mt-3">
            <View className="flex-1"><Button label="Save" loading={save.isPending} onPress={() => save.mutate()} /></View>
            <View className="flex-1"><Button variant="ghost" label="Cancel" onPress={() => setEditing(false)} /></View>
          </View>
        </View>
      ) : showGuide ? (
        <View className="mt-4">
          <Text className="text-text-primary font-body-medium text-sm mb-2">Side photo</Text>
          {SIDE_TIPS.map(([icon, text]) => (
            <View key={text} className="flex-row items-center gap-3 mt-1.5">
              <Ionicons name={icon} size={16} color={palette.accent} />
              <Text className="text-text-primary font-body text-sm flex-1">{text}</Text>
            </View>
          ))}
          <Text className="text-text-tertiary font-body text-xs mt-2 leading-4">
            The side photo is measured and then discarded; only the numbers are kept.
          </Text>
          <View className="flex-row gap-3 mt-3">
            <View className="flex-1"><Button icon="camera-outline" label="Take photo" loading={estimate.isPending} onPress={() => void pickSide(true)} /></View>
            <View className="flex-1"><Button variant="secondary" icon="images-outline" label="Choose" disabled={estimate.isPending} onPress={() => void pickSide(false)} /></View>
          </View>
        </View>
      ) : (
        <View className="gap-2 mt-4">
          <Button icon="body-outline" label="Estimate from a side photo" onPress={() => setShowGuide(true)} />
          <Button variant="secondary" icon="create-outline" label="Type my measurements" onPress={startEditing} />
        </View>
      )}

      <Text className="text-text-tertiary font-body text-xs mt-3 leading-4">{data.method} Estimates are shown as ranges until they have been checked against a tape measure.</Text>
    </View>
  );
}
