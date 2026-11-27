import { useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Modal } from '@/components/ui/Modal';
import { useToastStore } from '@/components/ui/Toast';
import { useThemeColors } from '@/hooks/useThemeColors';
import { authService, moderationService, tryonService } from '@/services';
import { apiErrorMessage } from '@/services/api';
import { useAuthStore } from '@/store/authStore';
import type { MainStackParamList } from '@/navigation/MainNavigator';
import { SettingsScreen } from './ProfileScreen';

/** Privacy and data (ENGINEERING_PLAN 4.3 / 4.7): policy, body data, sign-ins, account deletion. */
export function PrivacyScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<MainStackParamList>>();
  const palette = useThemeColors();
  const queryClient = useQueryClient();
  const showToast = useToastStore((s) => s.show);
  const expireSession = useAuthStore((s) => s.expireSession);
  const [confirm, setConfirm] = useState<'body' | 'everywhere' | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const blocked = useQuery({ queryKey: ['blocked-users'], queryFn: () => moderationService.blocked() });

  const run = async (action: () => Promise<void>, fallback: string) => {
    setBusy(true);
    try {
      await action();
    } catch (error) {
      showToast(apiErrorMessage(error, fallback), 'error');
    } finally {
      setBusy(false);
    }
  };

  const deleteBodyData = () => run(async () => {
    await tryonService.deleteAvatars();
    await queryClient.invalidateQueries({ queryKey: ['avatar'] });
    queryClient.invalidateQueries({ queryKey: ['tryon-saved'] });
    // Measurements and height are body data too (4.11).
    queryClient.invalidateQueries({ queryKey: ['measurements'] });
    queryClient.invalidateQueries({ queryKey: ['fit'] });
    useAuthStore.getState().updateProfile({ heightCm: undefined });
    showToast('Your body data was deleted', 'success');
  }, 'Could not delete your body data. Try again.');

  const logoutEverywhere = () => run(async () => {
    await authService.logoutEverywhere();
    await expireSession();
  }, 'Could not sign out of your other devices. Try again.');

  const deleteAccount = () => run(async () => {
    await authService.deleteAccount(password);
    queryClient.clear();
    await expireSession();
  }, 'Could not delete your account. Try again.');

  return (
    <SettingsScreen title="Privacy and data">
      <Pressable
        accessibilityRole="link"
        onPress={() => navigation.navigate('PrivacyPolicy')}
        className="flex-row items-center gap-3 min-h-14 border-y border-border"
      >
        <Ionicons name="document-text-outline" size={20} color={palette.textPrimary} />
        <Text className="text-text-primary font-body-medium text-base flex-1">Read the privacy policy</Text>
        <Ionicons name="chevron-forward" size={18} color={palette.textSecondary} />
      </Pressable>

      <Text accessibilityRole="header" className="text-text-primary font-display text-xl mt-8 mb-2">Body data</Text>
      <Text className="text-text-secondary font-body text-base leading-6 mb-3">
        Your body photos, avatar, body analysis and try-on looks from My Virtual Look.
      </Text>
      <Button variant="secondary" icon="trash-outline" label="Delete my body data" loading={busy && confirm === 'body'} onPress={() => setConfirm('body')} />

      <Text accessibilityRole="header" className="text-text-primary font-display text-xl mt-8 mb-2">Blocked people</Text>
      {blocked.data?.length ? blocked.data.map((person) => (
        <View key={person.id} className="flex-row items-center gap-3 min-h-14 border-b border-border">
          <Text className="text-text-primary font-body text-base flex-1">{person.name}</Text>
          <Button
            variant="ghost"
            size="sm"
            label="Unblock"
            onPress={() => void run(async () => {
              await moderationService.unblock(person.id);
              await queryClient.invalidateQueries();
            }, 'Could not unblock. Try again.')}
          />
        </View>
      )) : (
        <Text className="text-text-secondary font-body text-base leading-6">You haven&apos;t blocked anyone.</Text>
      )}

      <Text accessibilityRole="header" className="text-text-primary font-display text-xl mt-8 mb-2">Sign-ins</Text>
      <Text className="text-text-secondary font-body text-base leading-6 mb-3">
        Lost a phone or used a shared computer? End every sign-in, including this one.
      </Text>
      <Button variant="secondary" icon="log-out-outline" label="Log out of all devices" onPress={() => setConfirm('everywhere')} />

      <Text accessibilityRole="header" className="text-text-primary font-display text-xl mt-8 mb-2">Delete account</Text>
      <Text className="text-text-secondary font-body text-base leading-6 mb-3">
        Permanently deletes your account, wardrobe, photos, chats, listings and posts. Orders you took part in stay in the
        other person&apos;s history as &ldquo;Deleted user&rdquo;, without your address. This cannot be undone.
      </Text>
      {deleting ? (
        <View className="gap-3">
          <Input label="Your password" value={password} onChangeText={setPassword} isPassword autoComplete="current-password" textContentType="password" />
          <Button variant="destructive" label="Permanently delete my account" loading={busy} disabled={!password || busy} onPress={() => void deleteAccount()} />
          <Button variant="ghost" label="Cancel" onPress={() => { setDeleting(false); setPassword(''); }} />
        </View>
      ) : (
        <Button variant="destructive" icon="warning-outline" label="Delete my account" onPress={() => setDeleting(true)} />
      )}

      <Modal
        visible={confirm === 'body'}
        onClose={() => setConfirm(null)}
        title="Delete your body data?"
        message="This permanently removes your body photos, avatar, body analysis and every try-on look. Your wardrobe is not affected."
        confirmLabel="Delete"
        destructive
        onConfirm={() => { setConfirm(null); void deleteBodyData(); }}
      />
      <Modal
        visible={confirm === 'everywhere'}
        onClose={() => setConfirm(null)}
        title="Log out of all devices?"
        message="Every device signed in to AURA, including this one, will need to sign in again."
        confirmLabel="Log out everywhere"
        onConfirm={() => { setConfirm(null); void logoutEverywhere(); }}
      />
    </SettingsScreen>
  );
}
