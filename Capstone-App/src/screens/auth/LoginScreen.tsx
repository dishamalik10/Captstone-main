import { useState, useEffect } from 'react';
import { Alert, View, Text, Pressable, Switch } from 'react-native';
import * as LocalAuthentication from 'expo-local-authentication';
import { Ionicons } from '@expo/vector-icons';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { AuthScaffold, OrDivider } from '@/components/shared/AuthScaffold';
import { validateEmail } from '@/utils/helpers';
import { hapticLight } from '@/utils/haptics';
import { useThemeColors } from '@/hooks/useThemeColors';

interface LoginScreenProps {
  onLogin: (email: string, password: string) => void;
  onSignUp: () => void;
  onForgotPassword: () => void;
  loading?: boolean;
}

const SOCIAL = [
  { id: 'google', label: 'Continue with Google', icon: 'logo-google' as const },
  { id: 'apple', label: 'Continue with Apple', icon: 'logo-apple' as const },
  { id: 'facebook', label: 'Continue with Facebook', icon: 'logo-facebook' as const },
];

export function LoginScreen({ onLogin, onSignUp, onForgotPassword, loading }: LoginScreenProps) {
  const palette = useThemeColors();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(false);
  const [biometricAvailable, setBiometricAvailable] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    LocalAuthentication.hasHardwareAsync().then(setBiometricAvailable);
  }, []);

  const handleLogin = () => {
    const e: Record<string, string> = {};
    if (!validateEmail(email)) e.email = 'Enter a valid email address';
    if (!password) e.password = 'Enter your password';
    setErrors(e);
    if (Object.keys(e).length === 0) onLogin(email, password);
  };

  const handleBiometric = async () => {
    const result = await LocalAuthentication.authenticateAsync({
      promptMessage: 'Login with biometrics',
    });
    if (result.success) {
      Alert.alert('Sign in once first', 'Biometrics can unlock a previously saved authenticated session.');
    }
  };

  return (
    <AuthScaffold
      title="Welcome back"
      subtitle="Sign in to your wardrobe."
      footer={
        <Pressable accessibilityRole="link" accessibilityLabel="Go to sign up" onPress={onSignUp} className="items-center py-5">
          <Text className="text-text-secondary font-body text-base">
            New to AURA? <Text className="text-text-primary font-body-semibold underline">Create an account</Text>
          </Text>
        </Pressable>
      }
    >
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
        autoComplete="password"
        textContentType="password"
        error={errors.password}
        onSubmitEditing={handleLogin}
      />

      <View className="flex-row items-center justify-between mb-6">
        <View className="flex-row items-center gap-2">
          <Switch
            accessibilityLabel="Remember me"
            value={rememberMe}
            onValueChange={setRememberMe}
            trackColor={{ true: palette.accent, false: palette.border }}
            thumbColor={palette.surface}
            ios_backgroundColor={palette.border}
          />
          <Text className="text-text-secondary font-body text-sm">Remember me</Text>
        </View>
        <Pressable accessibilityRole="link" accessibilityLabel="Forgot password" onPress={onForgotPassword} hitSlop={10}>
          <Text className="text-text-primary font-body-medium text-sm underline">Forgot password?</Text>
        </Pressable>
      </View>

      <Button label="Log in" size="lg" onPress={handleLogin} loading={loading} />

      {biometricAvailable && (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Biometric login"
          onPress={() => {
            hapticLight();
            handleBiometric();
          }}
          className="flex-row items-center justify-center min-h-12 mt-3 gap-2 rounded-sm hover:bg-surface-raised"
        >
          <Ionicons name="finger-print" size={20} color={palette.accent} />
          <Text className="text-text-primary font-body-medium">Use biometric login</Text>
        </Pressable>
      )}

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
