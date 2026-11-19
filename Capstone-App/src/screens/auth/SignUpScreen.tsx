import { useState } from 'react';
import { Alert, View, Text, Pressable } from 'react-native';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { AuthScaffold, OrDivider } from '@/components/shared/AuthScaffold';
import { getPasswordStrength, validateEmail } from '@/utils/helpers';
import { PasswordStrength } from '@/components/shared/PasswordStrength';

interface SignUpScreenProps {
  onSignUp: (data: { fullName: string; email: string; password: string }) => void;
  onLogin: () => void;
  loading?: boolean;
}

const SOCIAL = [
  { id: 'google', label: 'Continue with Google', icon: 'logo-google' as const },
  { id: 'apple', label: 'Continue with Apple', icon: 'logo-apple' as const },
  { id: 'facebook', label: 'Continue with Facebook', icon: 'logo-facebook' as const },
];

export function SignUpScreen({ onSignUp, onLogin, loading }: SignUpScreenProps) {
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});

  const validate = () => {
    const e: Record<string, string> = {};
    if (!fullName.trim()) e.fullName = 'Enter your name';
    if (!validateEmail(email)) e.email = 'Enter a valid email address';
    if (password.length < 8) e.password = 'Use at least 8 characters';
    if (password !== confirmPassword) e.confirmPassword = 'Passwords do not match';
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const handleSubmit = () => {
    if (validate()) onSignUp({ fullName, email, password });
  };

  return (
    <AuthScaffold
      title="Create your account"
      subtitle="Start with a few pieces. AURA styles the rest."
      footer={
        <Pressable accessibilityRole="link" accessibilityLabel="Go to login" onPress={onLogin} className="items-center py-5">
          <Text className="text-text-secondary font-body text-base">
            Already have an account? <Text className="text-text-primary font-body-semibold underline">Log in</Text>
          </Text>
        </Pressable>
      }
    >
      <Input label="Full name" value={fullName} onChangeText={setFullName} autoComplete="name" textContentType="name" error={errors.fullName} />
      <Input
        label="Email"
        value={email}
        onChangeText={setEmail}
        keyboardType="email-address"
        autoCapitalize="none"
        autoComplete="email"
        textContentType="emailAddress"
        error={errors.email}
      />
      <Input
        label="Password"
        value={password}
        onChangeText={setPassword}
        isPassword
        autoComplete="new-password"
        textContentType="newPassword"
        error={errors.password}
        hint={password ? undefined : 'At least 8 characters'}
        containerClassName={password ? 'mb-2' : undefined}
      />
      {password.length > 0 && <PasswordStrength {...getPasswordStrength(password)} />}
      <Input
        label="Confirm password"
        value={confirmPassword}
        onChangeText={setConfirmPassword}
        isPassword
        autoComplete="new-password"
        textContentType="newPassword"
        error={errors.confirmPassword}
        onSubmitEditing={handleSubmit}
      />

      <Button label="Create account" size="lg" onPress={handleSubmit} loading={loading} className="mt-2" />

      <OrDivider />

      <View className="gap-3">
        {SOCIAL.map((s) => (
          <Button
            key={s.id}
            variant="secondary"
            label={s.label}
            icon={s.icon}
            onPress={() => {
              Alert.alert('Not configured', `${s.label} requires its provider credentials.`);
            }}
          />
        ))}
      </View>
    </AuthScaffold>
  );
}
