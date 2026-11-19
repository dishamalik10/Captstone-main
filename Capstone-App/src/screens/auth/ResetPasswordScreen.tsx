import { useState } from 'react';
import { View, Text } from 'react-native';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { Ionicons } from '@expo/vector-icons';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { AuthScaffold } from '@/components/shared/AuthScaffold';
import { ScreenWrapper } from '@/components/shared/ScreenWrapper';
import { PasswordStrength } from '@/components/shared/PasswordStrength';
import { getPasswordStrength } from '@/utils/helpers';
import { useThemeColors } from '@/hooks/useThemeColors';
import { layout, motion } from '@/constants/theme';

interface ResetPasswordScreenProps {
  onReset: (password: string) => void;
  onBack: () => void;
  loading?: boolean;
}

export function ResetPasswordScreen({ onReset, onBack, loading }: ResetPasswordScreenProps) {
  const palette = useThemeColors();
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [done, setDone] = useState(false);
  const [error, setError] = useState('');
  const strength = getPasswordStrength(password);

  const handleReset = () => {
    if (password.length < 8) {
      setError('Use at least 8 characters');
      return;
    }
    if (password !== confirm) {
      setError('Passwords do not match');
      return;
    }
    onReset(password);
    setDone(true);
  };

  if (done) {
    return (
      <ScreenWrapper className="flex-1 items-center justify-center px-6">
        <Animated.View entering={FadeInDown.duration(motion.long)} className="items-center px-6 w-full self-center" style={{ maxWidth: layout.form }}>
          <View className="w-20 h-20 rounded-full border border-border items-center justify-center mb-6">
            <Ionicons name="checkmark" size={32} color={palette.success} />
          </View>
          <Text accessibilityRole="header" className="text-text-primary font-display text-3xl mb-3 text-center">
            Password updated
          </Text>
          <Text className="text-text-secondary font-body text-base text-center mb-8">
            You can now log in with your new password.
          </Text>
          <Button label="Back to log in" onPress={onBack} />
        </Animated.View>
      </ScreenWrapper>
    );
  }

  return (
    <AuthScaffold title="Choose a new password" subtitle="Make it at least 8 characters." onBack={onBack}>
      <Input
        label="New password"
        value={password}
        onChangeText={setPassword}
        isPassword
        autoComplete="new-password"
        error={error}
        containerClassName={password ? 'mb-2' : undefined}
      />
      {password.length > 0 && <PasswordStrength score={strength.score} label={strength.label} />}
      <Input label="Confirm password" value={confirm} onChangeText={setConfirm} isPassword autoComplete="new-password" />
      <Button label="Update password" size="lg" onPress={handleReset} loading={loading} className="mt-2 mb-3" />
      <Button variant="ghost" label="Back to log in" onPress={onBack} />
    </AuthScaffold>
  );
}
