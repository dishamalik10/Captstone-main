import { useState } from 'react';
import { Modal as RNModal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { useToastStore } from '@/components/ui/Toast';
import { useThemeColors } from '@/hooks/useThemeColors';
import { moderationService, type ReportReason, type ReportTarget } from '@/services';
import { apiErrorMessage } from '@/services/api';
import { withAlpha } from '@/constants/theme';

const REASONS: { value: ReportReason; label: string }[] = [
  { value: 'scam', label: 'Scam or fraud' },
  { value: 'spam', label: 'Spam' },
  { value: 'harassment', label: 'Harassment or bullying' },
  { value: 'offensive', label: 'Offensive or explicit' },
  { value: 'prohibited_item', label: 'Fake or prohibited item' },
  { value: 'other', label: 'Something else' },
];

interface ReportSheetProps {
  visible: boolean;
  onClose: () => void;
  /** What is being reported; omit to offer only "Block". */
  target?: { type: ReportTarget; id: string; label: string };
  /** The person behind it, who can be blocked. */
  user?: { id: string; name: string };
  /** Called after a block, e.g. to leave the screen. */
  onBlocked?: () => void;
}

/** Report something and/or block its owner (ENGINEERING_PLAN 4.4). */
export function ReportSheet({ visible, onClose, target, user, onBlocked }: ReportSheetProps) {
  const palette = useThemeColors();
  const queryClient = useQueryClient();
  const showToast = useToastStore((s) => s.show);
  const [reason, setReason] = useState<ReportReason | null>(null);
  const [details, setDetails] = useState('');
  const [busy, setBusy] = useState(false);

  const close = () => {
    setReason(null);
    setDetails('');
    onClose();
  };

  const run = async (action: () => Promise<void>, done: string, fallback: string) => {
    setBusy(true);
    try {
      await action();
      showToast(done, 'success');
      close();
    } catch (error) {
      showToast(apiErrorMessage(error, fallback), 'error');
    } finally {
      setBusy(false);
    }
  };

  const sendReport = () => target && reason && run(
    () => moderationService.report(target.type, target.id, reason, details),
    'Thanks. We will review this report.',
    'Could not send the report. Try again.',
  );

  const block = () => user && run(async () => {
    await moderationService.block(user.id);
    await queryClient.invalidateQueries();
    onBlocked?.();
  }, `${user.name} is blocked`, 'Could not block this user. Try again.');

  return (
    <RNModal visible={visible} transparent animationType="slide" onRequestClose={close} statusBarTranslucent>
      <Pressable accessibilityLabel="Dismiss" onPress={close} style={[StyleSheet.absoluteFill, { backgroundColor: withAlpha(palette.scrim, 0.4) }]} />
      <View accessibilityViewIsModal className="mt-auto bg-surface rounded-t-lg border-t border-border w-full max-w-xl self-center" style={{ maxHeight: '85%' }}>
        <ScrollView contentContainerStyle={{ padding: 20, paddingBottom: 32 }} keyboardShouldPersistTaps="handled">
          {target && (
            <>
              <Text accessibilityRole="header" className="text-text-primary font-display text-2xl mb-1">Report {target.label}</Text>
              <Text className="text-text-secondary font-body text-sm mb-4">Reports are private. The other person is not told who sent it.</Text>
              {REASONS.map((option) => (
                <Pressable
                  key={option.value}
                  accessibilityRole="radio"
                  accessibilityState={{ checked: reason === option.value }}
                  onPress={() => setReason(option.value)}
                  className="flex-row items-center gap-3 min-h-12 border-b border-border"
                >
                  <Ionicons name={reason === option.value ? 'radio-button-on' : 'radio-button-off'} size={20} color={reason === option.value ? palette.accent : palette.textSecondary} />
                  <Text className="text-text-primary font-body text-base">{option.label}</Text>
                </Pressable>
              ))}
              <View className="mt-4 gap-3">
                <Input label="Anything else we should know? (optional)" value={details} onChangeText={setDetails} maxLength={1000} multiline />
                <Button label="Send report" loading={busy} disabled={!reason || busy} onPress={() => void sendReport()} />
              </View>
            </>
          )}
          {user && (
            <View className={target ? 'mt-6 pt-6 border-t border-border' : ''}>
              <Text className="text-text-secondary font-body text-sm mb-3">
                Blocking {user.name} hides their listings, posts and chats from you, and neither of you can message the other.
                You can unblock them in Privacy and data.
              </Text>
              <Button variant="destructive" icon="ban-outline" label={`Block ${user.name}`} disabled={busy} onPress={() => void block()} />
            </View>
          )}
          <View className="mt-3">
            <Button variant="ghost" label="Cancel" onPress={close} />
          </View>
        </ScrollView>
      </View>
    </RNModal>
  );
}

/** The "…" header button that opens a ReportSheet. */
export function ReportButton({ onPress, label = 'Report or block' }: { onPress: () => void; label?: string }) {
  const palette = useThemeColors();
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={label} onPress={onPress} className="w-11 h-11 items-center justify-center rounded-full">
      <Ionicons name="ellipsis-horizontal" size={22} color={palette.textPrimary} />
    </Pressable>
  );
}
