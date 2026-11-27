import { useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Alert, Platform, Pressable, ScrollView, Text, View, useWindowDimensions } from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation, useRoute, type RouteProp } from '@react-navigation/native';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ScreenWrapper } from '@/components/shared/ScreenWrapper';
import { Header } from '@/components/shared/Header';
import { AppImage } from '@/components/shared/AppImage';
import { Button } from '@/components/ui/Button';
import { Chip } from '@/components/ui/Chip';
import { Modal } from '@/components/ui/Modal';
import { useToastStore } from '@/components/ui/Toast';
import { OCCASIONS } from '@/constants/categories';
import { layout } from '@/constants/theme';
import { useOutfitAI, useOutfitRecommendations, useWeather } from '@/hooks';
import { useThemeColors } from '@/hooks/useThemeColors';
import { authService, fitService, tryonService } from '@/services';
import { FitAdviceCard } from '@/components/fit/FitAdviceCard';
import { MeasurementsCard } from '@/components/fit/MeasurementsCard';
import { useAuthStore } from '@/store/authStore';
import type { AvatarView, BodyAnalysis, Occasion, Outfit, TryOnRender, VirtualAvatar } from '@/types';
import { hapticLight, hapticMedium } from '@/utils/haptics';
import { cn } from '@/utils/helpers';
import type { MainStackParamList } from '@/navigation/MainNavigator';

const SHAPE_LABEL: Record<string, string> = {
  hourglass: 'Hourglass',
  rectangle: 'Rectangle',
  pear: 'Pear',
  apple: 'Apple',
  athletic: 'Inverted triangle',
};

function errorDetail(error: unknown, fallback: string): string {
  return (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? fallback;
}

export function VirtualLookScreen() {
  const navigation = useNavigation();
  const route = useRoute<RouteProp<MainStackParamList, 'VirtualLook'>>();
  const palette = useThemeColors();
  const showToast = useToastStore((s) => s.show);
  const queryClient = useQueryClient();
  const userId = useAuthStore((s) => s.user?.id);
  const { width } = useWindowDimensions();
  const contentWidth = Math.min(width - 32, layout.reading);

  const [view, setView] = useState<AvatarView>('front');
  const [occasion, setOccasion] = useState<Occasion>(route.params?.occasion ?? 'casual');
  const [index, setIndex] = useState(0);
  const [deck, setDeck] = useState<Outfit[] | null>(null);
  const [showBefore, setShowBefore] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  // Body-photo consent (4.3): asked before the first photo, recorded by the server.
  const [consentAccepted, setConsentAccepted] = useState(false);
  const [pendingPick, setPendingPick] = useState<{ target: AvatarView; useCamera: boolean } | null>(null);
  const seen = useRef<Set<string>>(new Set());

  const avatarQuery = useQuery({ queryKey: ['avatar'], queryFn: () => tryonService.getAvatars() });
  const avatars = avatarQuery.data?.avatars ?? {};
  const status = avatarQuery.data?.status;
  const avatar = avatars[view];
  const frontAvatar = avatars.front;

  const { data: outfits, isLoading: outfitsLoading } = useOutfitRecommendations(occasion);
  const { data: weather } = useWeather();
  const { feedbackMutation, alternativesMutation } = useOutfitAI();

  useEffect(() => {
    if (!outfits) return;
    setDeck(outfits);
    seen.current = new Set(outfits.map((o) => o.id));
    const wanted = route.params?.outfitId ? outfits.findIndex((o) => o.id === route.params?.outfitId) : -1;
    setIndex(wanted >= 0 ? wanted : 0);
  }, [outfits, route.params?.outfitId]);

  const looks = deck ?? outfits ?? [];
  const outfit = looks[Math.min(index, Math.max(0, looks.length - 1))];

  // -- render the selected outfit on the avatar ---------------------------------------
  const [renderId, setRenderId] = useState<string | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const startRender = useMutation({
    mutationFn: (o: Outfit) => tryonService.startRender(o.itemIds, view, o.id),
    onMutate: () => setStartError(null),
    onSuccess: (render) => setRenderId(render.id),
    // e.g. 429: one look at a time, a daily limit, or a full queue. Show the server's reason.
    onError: (error) => {
      setRenderId(null); // e.g. "Try again" on a failed look: show the reason with the start button
      setStartError(errorDetail(error, 'This look could not be started. Try again.'));
    },
  });
  const canRender = Boolean(avatar && status?.tryonReady && outfit);
  useEffect(() => {
    // Renders are started only when the user asks (each new one counts towards a daily
    // limit). A look rendered before is served from the cache instantly when re-requested.
    setRenderId(null);
    setStartError(null);
    setShowBefore(false);
  }, [outfit?.id, avatar?.id, status?.tryonReady, view]);

  const renderQuery = useQuery({
    queryKey: ['tryon', renderId],
    queryFn: () => tryonService.getRender(renderId!),
    enabled: Boolean(renderId),
    refetchInterval: (query) => {
      const state = (query.state.data as TryOnRender | undefined)?.status;
      return state === 'queued' || state === 'running' ? 2000 : false;
    },
  });
  const render = renderQuery.data;

  const savedQuery = useQuery({ queryKey: ['tryon-saved'], queryFn: () => tryonService.savedLooks() });

  // -- avatar upload ------------------------------------------------------------------
  const upload = useMutation({
    mutationFn: ({ asset, target, consent }: { asset: ImagePicker.ImagePickerAsset; target: AvatarView; consent: boolean }) =>
      tryonService.uploadAvatar({ uri: asset.uri, fileName: asset.fileName, mimeType: asset.mimeType, file: (asset as { file?: File }).file }, target, consent),
    onSuccess: async (created) => {
      await queryClient.invalidateQueries({ queryKey: ['avatar'] });
      queryClient.invalidateQueries({ queryKey: ['tryon-saved'] });
      setView(created.view);
      showToast(created.view === 'front' ? 'Your avatar is ready' : 'Side view added', 'success');
    },
    onError: (error) => showToast(errorDetail(error, 'Could not use that photo'), 'error'),
  });

  const pickPhoto = async (target: AvatarView, useCamera: boolean, consentJustGiven = false) => {
    hapticLight();
    const consent = consentJustGiven || consentAccepted || Boolean(avatarQuery.data?.consentGiven);
    if (!consent) {
      setPendingPick({ target, useCamera });
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
    const asset = result.assets[0];
    if (asset.fileSize && asset.fileSize > 10 * 1024 * 1024) {
      showToast('That photo is over 10 MB. Choose a smaller one.', 'error');
      return;
    }
    if (asset.width && asset.height && asset.height < asset.width) {
      showToast('Use a portrait (vertical) full-body photo.', 'error');
      return;
    }
    upload.mutate({ asset, target, consent: true });
  };

  const removeAvatar = useMutation({
    mutationFn: () => tryonService.deleteAvatars(),
    onSuccess: () => {
      setRenderId(null);
      setConsentAccepted(false); // deleting body data withdraws consent
      // Measurements and height are body data too (4.11).
      useAuthStore.getState().updateProfile({ heightCm: undefined });
      queryClient.invalidateQueries({ queryKey: ['measurements'] });
      queryClient.invalidateQueries({ queryKey: ['fit'] });
      queryClient.invalidateQueries({ queryKey: ['avatar'] });
      queryClient.invalidateQueries({ queryKey: ['tryon-saved'] });
      showToast('Your body data was deleted', 'success');
    },
    onError: (error) => showToast(errorDetail(error, 'Could not delete your body data. Try again.'), 'error'),
  });

  // -- look actions -------------------------------------------------------------------
  const saveLook = useMutation({
    mutationFn: async () => {
      if (!render || !outfit) throw new Error('No look');
      const saved = await tryonService.saveRender(render.id, true);
      // Saving is also a "save" reaction for the personalised ranker.
      await feedbackMutation.mutateAsync({ outfit, action: 'save' }).catch(() => undefined);
      return saved;
    },
    onSuccess: (saved) => {
      hapticMedium();
      queryClient.setQueryData(['tryon', saved.id], saved);
      queryClient.invalidateQueries({ queryKey: ['tryon-saved'] });
      showToast('Look saved', 'success');
    },
    onError: () => showToast('Could not save this look', 'error'),
  });

  const tryAnother = async () => {
    hapticLight();
    if (index < looks.length - 1) {
      setIndex(index + 1);
      return;
    }
    try {
      const alternatives = await alternativesMutation.mutateAsync({
        occasion,
        excludeRecommendationIds: [...seen.current],
        temperature: weather?.temperature,
        condition: weather?.condition,
      });
      if (!alternatives.length) {
        showToast('No other combinations for this occasion', 'info');
        return;
      }
      alternatives.forEach((o) => seen.current.add(o.id));
      setDeck([...looks, ...alternatives]);
      setIndex(looks.length);
    } catch (error) {
      showToast(errorDetail(error, 'Could not find another outfit'), 'error');
    }
  };

  const applyAnalysis = useMutation({
    mutationFn: async (analysis: BodyAnalysis) => {
      const updated = await authService.updateProfile({
        bodyShape: analysis.bodyShape,
        ...(analysis.skinTone ? { skinTone: analysis.skinTone.tone } : {}),
      });
      useAuthStore.getState().updateProfile(updated);
    },
    onSuccess: () => showToast('Saved to your profile; the stylist will use it', 'success'),
    onError: () => showToast('Could not update your profile', 'error'),
  });

  const busy = upload.isPending;
  const stageHeight = contentWidth * (4 / 3);

  return (
    <ScreenWrapper loading={avatarQuery.isLoading}>
      <Header title="My Virtual Look" subtitle="Your outfits, on you" showBack onBack={() => navigation.goBack()} />
      <ScrollView contentContainerStyle={{ paddingBottom: 64 }} showsVerticalScrollIndicator={false}>
        <View className="px-4 pt-5 self-center w-full" style={{ maxWidth: layout.reading + 32 }}>
          {!frontAvatar ? (
            <AvatarIntro
              busy={busy}
              analysisReady={status?.bodyAnalysisReady ?? false}
              onCamera={() => void pickPhoto('front', true)}
              onLibrary={() => void pickPhoto('front', false)}
            />
          ) : (
            <>
              {/* View toggle */}
              <View className="flex-row gap-2 mb-3">
                {(['front', 'side'] as AvatarView[]).map((v) => (
                  <Chip key={v} label={v === 'front' ? 'Front' : 'Side'} icon={v === 'front' ? 'person-outline' : 'swap-horizontal-outline'} selected={view === v} onPress={() => setView(v)} />
                ))}
              </View>

              {/* Stage: avatar wearing the outfit */}
              <View className="rounded-md overflow-hidden border border-border bg-surface" style={{ width: contentWidth, height: stageHeight }}>
                {!avatar ? (
                  <View className="flex-1 items-center justify-center px-8">
                    <Ionicons name="swap-horizontal-outline" size={28} color={palette.accent} />
                    <Text className="text-text-primary font-display text-xl text-center mt-3">Add a side view</Text>
                    <Text className="text-text-secondary font-body text-sm text-center mt-2">
                      Stand side-on, full body in frame. Outfits will render on this view too.
                    </Text>
                    <View className="flex-row gap-2 mt-5">
                      <Button variant="secondary" icon="camera-outline" label="Take photo" onPress={() => void pickPhoto('side', true)} loading={busy} />
                      <Button variant="ghost" icon="images-outline" label="Choose" onPress={() => void pickPhoto('side', false)} />
                    </View>
                  </View>
                ) : (
                  <>
                    <AppImage
                      source={{ uri: render?.status === 'done' && render.imageUrl && !showBefore ? render.imageUrl : avatar.imageUrl }}
                      style={{ width: '100%', height: '100%' }}
                      contentFit="contain"
                      accessibilityLabel={render?.status === 'done' && !showBefore ? 'Your avatar wearing the selected outfit' : 'Your avatar'}
                    />
                    <RenderOverlay render={render} starting={startRender.isPending} enabled={status?.enabled ?? false} tryonReady={status?.tryonReady ?? false} missing={status?.missingFiles ?? []} />
                    {render?.status === 'done' && (
                      <Pressable
                        accessibilityRole="button"
                        accessibilityLabel={showBefore ? 'Show the look' : 'Show my photo without the outfit'}
                        onPressIn={() => setShowBefore(true)}
                        onPressOut={() => setShowBefore(false)}
                        className="absolute top-3 right-3 flex-row items-center gap-1.5 px-3 h-9 rounded-full bg-surface border border-border"
                      >
                        <Ionicons name="eye-outline" size={15} color={palette.textPrimary} />
                        <Text className="text-text-primary font-body-medium text-xs">Hold for before</Text>
                      </Pressable>
                    )}
                    {canRender && outfit && !render && !startRender.isPending && (
                      <View className="absolute left-4 right-4 bottom-4 gap-2">
                        {startError ? (
                          <View className="rounded-sm bg-surface border border-destructive p-3" accessibilityLiveRegion="polite">
                            <Text className="text-text-primary font-body text-xs">{startError}</Text>
                          </View>
                        ) : null}
                        <Button variant="primary" icon="sparkles-outline" label="Try it on" onPress={() => { hapticMedium(); startRender.mutate(outfit); }} />
                      </View>
                    )}
                    {render?.status === 'failed' && outfit && (
                      <View className="absolute left-4 right-4 bottom-4">
                        <Button variant="secondary" icon="refresh" label="Try again" onPress={() => startRender.mutate(outfit)} />
                      </View>
                    )}
                  </>
                )}
              </View>
              <Text className="text-text-tertiary font-body text-xs mt-2 leading-4">
                {status?.disclaimer ?? 'AI-generated visual preview, not a physical fit simulation.'}
              </Text>
              {render?.notRendered?.length ? (
                <Text className="text-text-tertiary font-body text-xs mt-1">Not drawn on the avatar: {render.notRendered.join(', ')}.</Text>
              ) : null}

              {/* Outfit navigation */}
              <View className="mt-6">
                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingBottom: 8 }}>
                  {OCCASIONS.map((o) => (
                    <Chip key={o.key} label={o.label} icon={o.icon as keyof typeof Ionicons.glyphMap} selected={occasion === o.key} onPress={() => { setOccasion(o.key); setIndex(0); }} />
                  ))}
                </ScrollView>
                <View className="flex-row items-center mt-3">
                  <NavButton icon="chevron-back" label="Previous outfit" disabled={index === 0} onPress={() => setIndex(Math.max(0, index - 1))} />
                  <View className="flex-1 px-3">
                    <Text className="text-text-primary font-display text-xl text-center">{outfit ? outfit.name : outfitsLoading ? 'Finding outfits…' : 'No outfit yet'}</Text>
                    {looks.length > 0 && (
                      <Text className="text-text-secondary font-body text-xs text-center mt-0.5 tabular-nums">{index + 1} of {looks.length}</Text>
                    )}
                  </View>
                  <NavButton icon="chevron-forward" label="Next outfit" disabled={index >= looks.length - 1} onPress={() => setIndex(Math.min(looks.length - 1, index + 1))} />
                </View>

                {/* Change outfit: every option in this slate */}
                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10, paddingVertical: 12 }}>
                  {looks.map((look, i) => (
                    <Pressable
                      key={look.id}
                      accessibilityRole="button"
                      accessibilityLabel={`Outfit ${i + 1}: ${look.itemImages?.map((p) => p.label).join(', ')}`}
                      accessibilityState={{ selected: i === index }}
                      onPress={() => { hapticLight(); setIndex(i); }}
                      className={cn('flex-row gap-1 p-1.5 rounded-sm border', i === index ? 'border-accent' : 'border-border')}
                    >
                      {(look.itemImages ?? []).slice(0, 4).map((piece) => (
                        <AppImage key={piece.url} source={{ uri: piece.url }} className="w-10 h-12 rounded-sm" contentFit="cover" />
                      ))}
                    </Pressable>
                  ))}
                </ScrollView>
                {outfit && (
                  <Text className="text-text-secondary font-body text-sm">
                    {outfit.itemImages?.map((p) => p.label).join(' · ')}
                  </Text>
                )}
                {outfit && userId && (
                  <View className="mt-2 gap-1" accessibilityLabel="Size advice for each piece">
                    {outfit.itemIds.map((itemId) => (
                      <FitAdviceCard key={itemId} compact label={outfit.itemImages?.find((p) => p.id === itemId)?.label} queryKey={['item', itemId]}
                        load={() => fitService.forItem(userId, itemId)} />
                    ))}
                  </View>
                )}

                <View className="flex-row gap-3 mt-4">
                  <View className="flex-1">
                    <Button
                      icon={render?.saved ? 'bookmark' : 'bookmark-outline'}
                      label={render?.saved ? 'Saved' : 'Save look'}
                      disabled={render?.status !== 'done' || render.saved}
                      loading={saveLook.isPending}
                      onPress={() => saveLook.mutate()}
                    />
                  </View>
                  <View className="flex-1">
                    <Button
                      variant="secondary"
                      icon="shuffle"
                      label="Try another outfit"
                      loading={alternativesMutation.isPending}
                      onPress={() => void tryAnother()}
                    />
                  </View>
                </View>
              </View>

              {/* Body analysis */}
              {frontAvatar.analysis && (
                <AnalysisCard
                  analysis={frontAvatar.analysis}
                  applying={applyAnalysis.isPending}
                  onApply={() => applyAnalysis.mutate(frontAvatar.analysis!)}
                />
              )}

              <MeasurementsCard />

              {/* Saved looks */}
              {(savedQuery.data?.length ?? 0) > 0 && (
                <View className="mt-8">
                  <Text accessibilityRole="header" className="text-text-primary font-display text-xl mb-3">Saved looks</Text>
                  <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10 }}>
                    {savedQuery.data!.map((look) => (
                      <AppImage key={look.id} source={{ uri: look.imageUrl }} style={{ width: 120, height: 160 }} className="rounded-sm border border-border" contentFit="cover" accessibilityLabel="Saved look" />
                    ))}
                  </ScrollView>
                </View>
              )}

              {/* Photo management */}
              <View className="mt-8 gap-2">
                <Button variant="secondary" icon="camera-outline" label={`Update ${view} photo`} loading={busy} onPress={() => void pickPhoto(view, false)} />
                <Button variant="ghost" icon="trash-outline" label="Delete my body data" onPress={() => setConfirmDelete(true)} />
                <Text className="text-text-tertiary font-body text-xs leading-4 mt-1">
                  Your photos stay on your AURA server, are shown only through private links that expire, and are never sent to an outside service.
                </Text>
              </View>
            </>
          )}
        </View>
      </ScrollView>
      <Modal
        visible={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        title="Delete your body data?"
        message="This permanently removes your body photos, avatar, body analysis and every try-on look. Your wardrobe is not affected."
        confirmLabel="Delete"
        onConfirm={() => { setConfirmDelete(false); removeAvatar.mutate(); }}
        destructive
      />
      <Modal
        visible={pendingPick !== null}
        onClose={() => setPendingPick(null)}
        title="Before you add a body photo"
        message={CONSENT_TEXT}
        confirmLabel="I confirm"
        cancelLabel="Not now"
        onConfirm={() => {
          const pick = pendingPick;
          setPendingPick(null);
          setConsentAccepted(true);
          if (pick) void pickPhoto(pick.target, pick.useCamera, true);
        }}
      />
    </ScreenWrapper>
  );
}

const CONSENT_TEXT =
  'Please confirm that:\n\n• this photo is of you,\n• you are 18 or over, and\n' +
  '• you agree to AURA storing your photo and the body analysis made from it on AURA\'s server, ' +
  'until you delete them with "Delete my body data" or delete your account.\n\n' +
  'Your photos are never shared with other users or sent to an outside service.';

function AvatarIntro({ busy, analysisReady, onCamera, onLibrary }: { busy: boolean; analysisReady: boolean; onCamera: () => void; onLibrary: () => void }) {
  const palette = useThemeColors();
  const tips: [keyof typeof Ionicons.glyphMap, string][] = [
    ['body-outline', 'Full body, head to feet, facing the camera'],
    ['hand-left-outline', 'Arms slightly away from your sides'],
    ['shirt-outline', 'Fitted clothes show your shape best'],
    ['sunny-outline', 'Good light and a plain background'],
  ];
  return (
    <View className="rounded-md border border-border bg-surface p-5">
      <Text accessibilityRole="header" className="text-text-primary font-display text-2xl">Create your avatar</Text>
      <Text className="text-text-secondary font-body text-sm mt-2 leading-5">
        Upload one full-body photo. AURA uses your own photo as your model, so your shape, skin tone and proportions stay exactly yours, and dresses it in the Stylist’s picks from your wardrobe.
      </Text>
      <View className="mt-4 gap-2.5">
        {tips.map(([icon, text]) => (
          <View key={text} className="flex-row items-center gap-3">
            <Ionicons name={icon} size={18} color={palette.accent} />
            <Text className="text-text-primary font-body text-sm flex-1">{text}</Text>
          </View>
        ))}
      </View>
      {busy ? (
        <View className="flex-row items-center gap-3 mt-6">
          <ActivityIndicator color={palette.accent} />
          <Text className="text-text-secondary font-body text-sm">Analysing your photo…</Text>
        </View>
      ) : (
        <View className="gap-2 mt-6">
          <Button icon="camera-outline" label="Take a photo" onPress={onCamera} disabled={!analysisReady} />
          <Button variant="secondary" icon="images-outline" label="Choose from library" onPress={onLibrary} disabled={!analysisReady} />
        </View>
      )}
      {!analysisReady && (
        <Text className="text-warning font-body text-xs mt-3">Body analysis models are not installed on the server yet.</Text>
      )}
      <Text className="text-text-tertiary font-body text-xs mt-4 leading-4">
        Your photo stays on your AURA server and is never sent to an outside service. You can delete it at any time.
      </Text>
    </View>
  );
}

function RenderOverlay({ render, starting, enabled, tryonReady, missing }: { render?: TryOnRender; starting: boolean; enabled: boolean; tryonReady: boolean; missing: string[] }) {
  const palette = useThemeColors();
  if (!enabled) {
    return (
      <View className="absolute left-3 right-3 bottom-3 rounded-sm bg-surface border border-border p-3">
        <Text className="text-text-primary font-body-medium text-sm">Try-on is turned off on this server</Text>
        <Text className="text-text-secondary font-body text-xs mt-1">
          It is off by default so AURA runs on 8 GB Macs. To use it, set AURA_TRYON_ENABLED=1 in Capstone_Agents/.env and restart the server.
        </Text>
      </View>
    );
  }
  if (!tryonReady) {
    return (
      <View className="absolute left-3 right-3 bottom-3 rounded-sm bg-surface border border-border p-3">
        <Text className="text-text-primary font-body-medium text-sm">Try-on model not installed</Text>
        <Text className="text-text-secondary font-body text-xs mt-1">
          On the server run: python -m training.download_tryon_models{missing.length ? ` (${missing.length} files missing)` : ''}
        </Text>
      </View>
    );
  }
  if (render?.status === 'failed') {
    return (
      <View className="absolute left-3 right-3 top-3 rounded-sm bg-surface border border-destructive p-3">
        <Text className="text-destructive font-body-medium text-sm">This look could not be rendered</Text>
        <Text className="text-text-secondary font-body text-xs mt-1">{render.error}</Text>
      </View>
    );
  }
  if (starting || render?.status === 'queued' || render?.status === 'running') {
    const pct = Math.round((render?.progress ?? 0) * 100);
    return (
      <View className="absolute left-3 right-3 bottom-3 rounded-sm bg-surface border border-border p-3" accessibilityLiveRegion="polite">
        <View className="flex-row items-center gap-2">
          <ActivityIndicator size="small" color={palette.accent} />
          <Text className="text-text-primary font-body-medium text-sm flex-1" numberOfLines={1}>
            {render?.stage || 'Starting…'}
          </Text>
          <Text className="text-text-secondary font-body text-xs tabular-nums">{pct}%</Text>
        </View>
        <View className="h-1.5 rounded-full bg-surface-raised mt-2 overflow-hidden">
          <View className="h-full bg-accent" style={{ width: `${Math.max(3, pct)}%` }} />
        </View>
        <Text className="text-text-tertiary font-body text-xs mt-1.5">Rendering runs on this computer and takes a few minutes per garment.</Text>
      </View>
    );
  }
  return null;
}

function NavButton({ icon, label, disabled, onPress }: { icon: keyof typeof Ionicons.glyphMap; label: string; disabled: boolean; onPress: () => void }) {
  const palette = useThemeColors();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={() => { hapticLight(); onPress(); }}
      className={cn('w-11 h-11 rounded-full border border-border items-center justify-center', disabled && 'opacity-40')}
    >
      <Ionicons name={icon} size={20} color={palette.textPrimary} />
    </Pressable>
  );
}

function AnalysisCard({ analysis, applying, onApply }: { analysis: BodyAnalysis; applying: boolean; onApply: () => void }) {
  const ratios = useMemo(() => [
    ['Shoulder : hip', analysis.ratios.shoulderToHip],
    ['Waist : hip', analysis.ratios.waistToHip],
    ['Torso : leg', analysis.ratios.torsoToLeg],
  ] as const, [analysis]);
  return (
    <View className="mt-8 rounded-md border border-border p-5">
      <Text accessibilityRole="header" className="text-text-primary font-display text-xl">Your proportions</Text>
      <Text className="text-text-secondary font-body text-xs mt-1">Estimated from your photo · {analysis.confidence} confidence</Text>
      <View className="flex-row items-baseline gap-2 mt-4">
        <Text className="text-text-primary font-display text-2xl">{SHAPE_LABEL[analysis.bodyShape] ?? analysis.bodyShape}</Text>
        <Text className="text-text-secondary font-body text-sm">silhouette</Text>
      </View>
      <Text className="text-text-secondary font-body text-sm mt-1">{analysis.bodyShapeReason}</Text>
      <View className="flex-row mt-4 border-t border-border">
        {ratios.map(([label, value], i) => (
          <View key={label} className={cn('flex-1 pt-3', i > 0 && 'pl-3 border-l border-border')}>
            <Text className="text-text-primary font-body-semibold text-lg tabular-nums">{value?.toFixed(2)}</Text>
            <Text className="text-text-secondary font-body text-xs">{label}</Text>
          </View>
        ))}
      </View>
      <Text className="text-text-secondary font-body text-sm mt-3">Torso length: {analysis.torsoLength}</Text>
      {analysis.skinTone && (
        <View className="flex-row items-center gap-2 mt-2">
          <View className="w-4 h-4 rounded-full border border-border" style={{ backgroundColor: analysis.skinTone.sampleHex }} />
          <Text className="text-text-secondary font-body text-sm">Skin depth: {analysis.skinTone.tone}</Text>
        </View>
      )}
      {analysis.warnings.map((w) => (
        <Text key={w} className="text-warning font-body text-xs mt-2">{w}</Text>
      ))}
      <Text className="text-text-tertiary font-body text-xs mt-3 leading-4">{analysis.method}</Text>
      <View className="mt-4">
        <Button variant="secondary" icon="checkmark" label="Use in my style profile" loading={applying} onPress={onApply} />
      </View>
    </View>
  );
}
