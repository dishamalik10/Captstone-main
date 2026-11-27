import { Linking, Text, View } from 'react-native';
import { Button } from '@/components/ui/Button';
import { AuthScaffold } from '@/components/shared/AuthScaffold';

const SUPPORT_EMAIL = 'support@wearbefore.com';

interface ForgotPasswordScreenProps {
  /** Kept for the navigator's API; AURA does not send reset emails yet. */
  onSend?: (email: string) => void;
  onBack: () => void;
  loading?: boolean;
}

/**
 * AURA can't send password-reset emails yet, so this screen says so plainly instead of
 * pretending a link was sent. The AURA team resets the password by hand
 * (Capstone_Agents/scripts/reset_password.py) after checking it is really the account owner.
 */
export function ForgotPasswordScreen({ onBack }: ForgotPasswordScreenProps) {
  return (
    <AuthScaffold
      title="Forgot your password?"
      subtitle="AURA can’t send reset emails yet. The AURA team can reset your password for you."
      onBack={onBack}
    >
      <View className="gap-2 mb-6">
        <Text className="text-text-secondary font-body text-base leading-6">
          Email us from the address you signed up with and ask for a password reset. We’ll reply with a new password; keep it in a password manager.
        </Text>
        <Text selectable className="text-text-primary font-body-medium text-base">{SUPPORT_EMAIL}</Text>
      </View>
      <Button
        label="Email support"
        size="lg"
        icon="mail-outline"
        onPress={() => void Linking.openURL(`mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent('AURA password reset')}`)}
        className="mb-3"
      />
      <Button variant="ghost" label="Back to log in" onPress={onBack} />
    </AuthScaffold>
  );
}
