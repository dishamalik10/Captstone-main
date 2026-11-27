import { useState } from 'react';
import { View, Text, Pressable } from 'react-native';
import Animated, { FadeInDown } from 'react-native-reanimated';
import * as ImagePicker from 'expo-image-picker';
import { Ionicons } from '@expo/vector-icons';
import { KeyboardAwareScroll } from '@/components/shared/KeyboardAwareScroll';
import { Avatar } from '@/components/ui/Avatar';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Chip } from '@/components/ui/Chip';
import { ScreenWrapper } from '@/components/shared/ScreenWrapper';
import { STYLE_PREFERENCES, BODY_SHAPES, SKIN_TONES, SIZES } from '@/constants/categories';
import type { StylePreference, BodyShape, SkinTone, Size, User } from '@/types';
import { hapticLight } from '@/utils/haptics';
import { cn } from '@/utils/helpers';
import { useThemeColors } from '@/hooks/useThemeColors';
import { apiErrorMessage } from '@/services/api';
import { layout, motion } from '@/constants/theme';

interface ProfileSetupScreenProps {
  completeLabel?: string;
  /** Optional: shows a close control (used when editing an existing profile). */
  onBack?: () => void;
  initialData?: Partial<User>;
  onComplete: (data: {
    avatarUrl?: string;
    fullName: string;
    stylePreferences: StylePreference[];
    heightCm: number;
    bodyShape: BodyShape;
    topSize: Size;
    bottomSize: Size;
    skinTone: SkinTone;
  }) => Promise<void> | void;
}

const STEPS = [
  { title: 'Your profile', subtitle: 'A name and, if you like, a photo.' },
  { title: 'Your style', subtitle: 'Pick any that feel like you. You can change these anytime.' },
  { title: 'Fit and sizing', subtitle: 'Used only to suggest proportions and sizes. Edit it whenever you like.' },
  { title: 'Colour profile', subtitle: 'Helps suggest colours you may enjoy. Your taste always comes first.' },
];

const BODY_NOTES: Record<string, string> = {
  hourglass: 'Shoulders and hips similar, defined waist',
  rectangle: 'Shoulders, waist and hips similar',
  pear: 'Hips wider than shoulders',
  apple: 'More volume through the middle',
  athletic: 'Broader shoulders, straighter hips',
};

export function ProfileSetupScreen({
  onComplete,
  completeLabel = 'Complete Setup',
  initialData,
  onBack,
}: ProfileSetupScreenProps) {
  const palette = useThemeColors();
  const [step, setStep] = useState(0);
  const [avatarUrl, setAvatarUrl] = useState<string | undefined>(initialData?.avatarUrl);
  const [fullName, setFullName] = useState(initialData?.fullName ?? '');
  const [styles, setStyles] = useState<StylePreference[]>(initialData?.stylePreferences ?? []);
  const [heightCm, setHeightCm] = useState(String(initialData?.heightCm ?? 178));
  const [useFt, setUseFt] = useState(false);
  const [bodyShape, setBodyShape] = useState<BodyShape>(initialData?.bodyShape ?? 'athletic');
  const [topSize, setTopSize] = useState<Size>(initialData?.topSize ?? 'M');
  const [bottomSize, setBottomSize] = useState<Size>(initialData?.bottomSize ?? 'M');
  const [skinTone, setSkinTone] = useState<SkinTone>(initialData?.skinTone ?? 'medium');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const pickImage = async () => {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      allowsEditing: true,
      aspect: [1, 1],
      quality: 0.8,
    });
    if (!result.canceled) setAvatarUrl(result.assets[0].uri);
  };

  const toggleStyle = (s: StylePreference) => {
    setStyles((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]));
  };

  const next = async () => {
    if (step < 3) {
      setStep(step + 1);
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      await onComplete({
          avatarUrl,
          fullName,
          stylePreferences: styles,
          heightCm: parseInt(heightCm, 10) || 178,
          bodyShape,
          topSize,
          bottomSize,
          skinTone,
      });
    } catch (error) {
      setSaveError(apiErrorMessage(error, 'Could not save your profile. Try again.'));
    } finally {
      setSaving(false);
    }
  };

  const column = { width: '100%', maxWidth: layout.form + 48, alignSelf: 'center' } as const;

  return (
    <ScreenWrapper className="flex-1">
      <View className="px-6 pt-4" style={column}>
        <View className="flex-row items-center justify-between mb-3 min-h-11">
          <Text className="text-text-secondary font-body text-sm tabular-nums">Step {step + 1} of 4</Text>
          {onBack && (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Go back"
              onPress={onBack}
              className="w-11 h-11 -mr-2 rounded-full items-center justify-center hover:bg-surface-raised"
            >
              <Ionicons name="close" size={22} color={palette.textPrimary} />
            </Pressable>
          )}
        </View>
        <View className="flex-row gap-1.5">
          {[0, 1, 2, 3].map((i) => (
            <View key={i} className={cn('flex-1 h-0.5 rounded-full', i <= step ? 'bg-accent' : 'bg-border')} />
          ))}
        </View>
      </View>

      <KeyboardAwareScroll>
        <Animated.View key={step} entering={FadeInDown.duration(motion.long)} className="px-6 pt-8" style={column}>
          <Text accessibilityRole="header" className="text-text-primary font-display text-4xl tracking-tight">
            {STEPS[step].title}
          </Text>
          <Text className="text-text-secondary font-body text-base mt-3 mb-8">{STEPS[step].subtitle}</Text>

          {step === 0 && (
            <View>
              <View className="items-center mb-8">
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={avatarUrl ? 'Change profile photo' : 'Upload profile photo'}
                  onPress={pickImage}
                  className="items-center"
                >
                  <Avatar uri={avatarUrl} name={fullName} size="xl" />
                  <View className="absolute bottom-0 right-0 w-8 h-8 rounded-full bg-primary items-center justify-center border-2 border-background">
                    <Ionicons name="camera" size={14} color={palette.primaryInk} />
                  </View>
                </Pressable>
                <Text className="text-text-secondary font-body text-sm mt-3">
                  {avatarUrl ? 'Tap to change' : 'Add a photo (optional)'}
                </Text>
              </View>
              <Input label="Display name" value={fullName} onChangeText={setFullName} autoComplete="name" />
            </View>
          )}

          {step === 1 && (
            <View className="flex-row flex-wrap">
              {STYLE_PREFERENCES.map((s) => (
                <Chip
                  key={s.key}
                  label={s.label}
                  selected={styles.includes(s.key)}
                  onPress={() => toggleStyle(s.key)}
                  icon={styles.includes(s.key) ? 'checkmark' : undefined}
                />
              ))}
            </View>
          )}

          {step === 2 && (
            <View>
              <View className="flex-row items-end gap-3 mb-2">
                <View className="flex-1">
                  <Input
                    label="Height (cm)"
                    value={heightCm}
                    onChangeText={setHeightCm}
                    keyboardType="numeric"
                    containerClassName="mb-0"
                  />
                </View>
                <View className="flex-row border border-border rounded-sm mb-0 overflow-hidden">
                  {(['cm', 'ft'] as const).map((unit) => {
                    const active = unit === 'ft' ? useFt : !useFt;
                    return (
                      <Pressable
                        key={unit}
                        accessibilityRole="button"
                        accessibilityState={{ selected: active }}
                        accessibilityLabel={`Use ${unit}`}
                        onPress={() => setUseFt(unit === 'ft')}
                        className={cn('w-12 h-14 items-center justify-center', active ? 'bg-primary' : 'bg-surface')}
                      >
                        <Text className={cn('font-body-medium text-sm', active ? 'text-primary-ink' : 'text-text-secondary')}>
                          {unit}
                        </Text>
                      </Pressable>
                    );
                  })}
                </View>
              </View>

              <Text className="text-text-primary font-body-semibold text-base mt-8 mb-1">Body shape</Text>
              <Text className="text-text-tertiary font-body text-sm mb-4">
                Every shape is a good shape. This only guides proportion suggestions.
              </Text>
              <View className="gap-2 mb-8" accessibilityRole="radiogroup">
                {BODY_SHAPES.map((b) => {
                  const selected = bodyShape === b.key;
                  return (
                    <Pressable
                      key={b.key}
                      accessibilityRole="radio"
                      accessibilityState={{ checked: selected }}
                      accessibilityLabel={b.label}
                      onPress={() => {
                        hapticLight();
                        setBodyShape(b.key);
                      }}
                      className={cn(
                        'flex-row items-center px-4 min-h-16 py-3 rounded-sm border',
                        selected ? 'border-primary bg-surface-raised' : 'border-border bg-surface hover:border-border-strong',
                      )}
                    >
                      <View className="flex-1 pr-3">
                        <Text className="text-text-primary font-body-medium text-base">{b.label}</Text>
                        <Text className="text-text-tertiary font-body text-sm mt-0.5">{BODY_NOTES[b.key]}</Text>
                      </View>
                      <View
                        className={cn(
                          'w-5 h-5 rounded-full border items-center justify-center',
                          selected ? 'border-primary' : 'border-border-strong',
                        )}
                      >
                        {selected && <View className="w-2.5 h-2.5 rounded-full bg-primary" />}
                      </View>
                    </Pressable>
                  );
                })}
              </View>

              <Text className="text-text-primary font-body-semibold text-base mb-3">Top size</Text>
              <View className="flex-row flex-wrap mb-6">
                {SIZES.map((s) => (
                  <Chip key={s} label={s} selected={topSize === s} onPress={() => setTopSize(s)} />
                ))}
              </View>
              <Text className="text-text-primary font-body-semibold text-base mb-3">Bottom size</Text>
              <View className="flex-row flex-wrap">
                {SIZES.map((s) => (
                  <Chip key={s} label={s} selected={bottomSize === s} onPress={() => setBottomSize(s)} />
                ))}
              </View>
            </View>
          )}

          {step === 3 && (
            <View>
              <View className="flex-row flex-wrap gap-y-6" accessibilityRole="radiogroup">
                {SKIN_TONES.map((t) => {
                  const selected = skinTone === t.key;
                  return (
                    <Pressable
                      key={t.key}
                      accessibilityRole="radio"
                      accessibilityState={{ checked: selected }}
                      accessibilityLabel={t.label}
                      onPress={() => {
                        hapticLight();
                        setSkinTone(t.key);
                      }}
                      className="w-1/3 items-center"
                    >
                      <View
                        className={cn(
                          'w-[72px] h-[72px] rounded-full items-center justify-center border-2',
                          selected ? 'border-primary' : 'border-transparent',
                        )}
                      >
                        <View
                          className="w-16 h-16 rounded-full items-center justify-center border border-border"
                          style={{ backgroundColor: t.color }}
                        >
                          {selected && (
                            <View className="w-7 h-7 rounded-full bg-background/80 items-center justify-center">
                              <Ionicons name="checkmark" size={16} color={palette.textPrimary} />
                            </View>
                          )}
                        </View>
                      </View>
                      <Text
                        className={cn(
                          'font-body text-sm mt-2',
                          selected ? 'text-text-primary font-body-medium' : 'text-text-secondary',
                        )}
                      >
                        {t.label}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>
              <View className="flex-row gap-3 mt-10 p-4 rounded-sm bg-surface-raised">
                <Ionicons name="information-circle-outline" size={18} color={palette.textSecondary} />
                <Text className="text-text-secondary font-body text-sm flex-1">
                  Colour suggestions are a starting point, not a rule. Wear what you love.
                </Text>
              </View>
            </View>
          )}
        </Animated.View>
      </KeyboardAwareScroll>

      <View className="px-6 pb-6 pt-3 border-t border-border" style={column}>
        {saveError && (
          <View className="flex-row items-center justify-center gap-2 mb-3" accessibilityLiveRegion="polite">
            <Ionicons name="alert-circle-outline" size={16} color={palette.destructive} />
            <Text className="text-destructive font-body text-sm text-center">{saveError}</Text>
          </View>
        )}
        <View className="flex-row gap-3">
          {step > 0 && (
            <Button variant="secondary" size="lg" label="Back" onPress={() => setStep(step - 1)} className="px-6" />
          )}
          <View className="flex-1">
            <Button
              label={step < 3 ? 'Continue' : completeLabel}
              size="lg"
              onPress={() => void next()}
              loading={saving}
            />
          </View>
        </View>
      </View>
    </ScreenWrapper>
  );
}
