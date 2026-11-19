import { useState } from 'react';
import { View, Text } from 'react-native';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { Ionicons } from '@expo/vector-icons';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { AuthScaffold } from '@/components/shared/AuthScaffold';
import { ScreenWrapper } from '@/components/shared/ScreenWrapper';
import { validateEmail } from '@/utils/helpers';
import { useThemeColors } from '@/hooks/useThemeColors';
import { layout, motion } from '@/constants/theme';

interface ForgotPasswordScreenProps {
  onSend: (email: string) => void;
  onBack: () => void;
  loading?: boolean;
}

export function ForgotPasswordScreen({ onSend, onBack, loading }: ForgotPasswordScreenProps) {
  const palette = useThemeColors();
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [error, setError] = useState('');

  const handleSend = () => {
    if (!validateEmail(email)) {
      setError('Enter a valid email address');
      return;
    }
    onSend(email);
    setSent(true);
  };

  if (sent) {
    return (
      <ScreenWrapper className="flex-1 items-center justify-center px-6">
        <Animated.View
          entering={FadeInDown.duration(motion.long)}
          className="items-center px-6 w-full self-center"
          style={{ maxWidth: layout.form }}
        >
          <View className="w-20 h-20 rounded-full border border-border items-center justify-center mb-6">
            <Ionicons name="mail-open-outline" size={30} color={palette.accent} />
          </View>
          <Text accessibilityRole="header" className="text-text-primary font-display text-3xl mb-3 text-center">
            Check your email
          </Text>
          <Text className="text-text-secondary font-body text-base text-center mb-8">
            If an account exists for {email}, a reset link is on its way.
          </Text>
          <Button label="Back to log in" onPress={onBack} />
        </Animated.View>
      </ScreenWrapper>
    );
  }

  return (
    <AuthScaffold
      title="Reset your password"
      subtitle="Enter your email and we’ll send you a reset link."
      onBack={onBack}
    >
      <Input
        label="Email"
        value={email}
        onChangeText={(t) => {
          setEmail(t);
          if (error) setError('');
        }}
        keyboardType="email-address"
        autoCapitalize="none"
        autoComplete="email"
        error={error}
        onSubmitEditing={handleSend}
      />
      <Button label="Send reset link" size="lg" onPress={handleSend} loading={loading} className="mt-2 mb-3" />
      <Button variant="ghost" label="Back to log in" onPress={onBack} />
    </AuthScaffold>
  );
}
