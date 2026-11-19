import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { LandingScreen } from '@/screens/landing/LandingScreen';
import { WelcomeScreen } from '@/screens/auth/WelcomeScreen';
import { OnboardingScreen } from '@/screens/onboarding/OnboardingScreen';
import { SignUpScreen } from '@/screens/auth/SignUpScreen';
import { LoginScreen } from '@/screens/auth/LoginScreen';
import { OTPScreen } from '@/screens/auth/OTPScreen';
import { ForgotPasswordScreen } from '@/screens/auth/ForgotPasswordScreen';
import { ResetPasswordScreen } from '@/screens/auth/ResetPasswordScreen';
import { ProfileSetupScreen } from '@/screens/onboarding/ProfileSetupScreen';
import { useAuth } from '@/hooks';
import { authService } from '@/services';
import { useThemeColors } from '@/hooks/useThemeColors';

export type AuthStackParamList = {
  Landing: undefined;
  Welcome: undefined;
  Onboarding: undefined;
  SignUp: undefined;
  Login: undefined;
  OTP: { email: string };
  ForgotPassword: undefined;
  ResetPassword: undefined;
  ProfileSetup: undefined;
};

const Stack = createNativeStackNavigator<AuthStackParamList>();

export function AuthNavigator() {
  const { loginMutation, signupMutation, updateProfile, logout } = useAuth();
  const palette = useThemeColors();

  return (
    <Stack.Navigator
      initialRouteName="Landing"
      screenOptions={{ headerShown: false, animation: 'fade', contentStyle: { backgroundColor: palette.background } }}
    >
      <Stack.Screen name="Landing">
        {({ navigation }) => (
          <LandingScreen
            onGetStarted={() => navigation.navigate('Welcome')}
            onStartStyling={() => navigation.navigate('SignUp')}
            onLogin={() => navigation.navigate('Login')}
          />
        )}
      </Stack.Screen>

      <Stack.Screen name="Welcome">
        {({ navigation }) => (
          <WelcomeScreen
            onGetStarted={() => navigation.navigate('Onboarding')}
            onLogin={() => navigation.navigate('Login')}
          />
        )}
      </Stack.Screen>

      <Stack.Screen name="Onboarding">
        {({ navigation }) => (
          <OnboardingScreen
            onComplete={() => navigation.navigate('SignUp')}
            onLogin={() => navigation.navigate('Login')}
          />
        )}
      </Stack.Screen>

      <Stack.Screen name="SignUp">
        {({ navigation }) => (
          <SignUpScreen
            loading={signupMutation.isPending}
            onSignUp={(data) => {
              signupMutation.mutate(data, {
                onSuccess: (result) => {
                  navigation.navigate('ProfileSetup');
                },
              });
            }}
            onLogin={() => navigation.navigate('Login')}
          />
        )}
      </Stack.Screen>

      <Stack.Screen name="OTP">
        {({ navigation, route }) => (
          <OTPScreen
            email={route.params.email}
            loading={false}
            onVerify={async () => {
              navigation.navigate('ProfileSetup');
            }}
            onResend={() => {}}
          />
        )}
      </Stack.Screen>

      <Stack.Screen name="Login">
        {({ navigation }) => (
          <LoginScreen
            loading={loginMutation.isPending}
            onLogin={(email, password) => {
              loginMutation.mutate({ email, password });
            }}
            onSignUp={() => navigation.navigate('SignUp')}
            onForgotPassword={() => navigation.navigate('ForgotPassword')}
          />
        )}
      </Stack.Screen>

      <Stack.Screen name="ForgotPassword">
        {({ navigation }) => (
          <ForgotPasswordScreen onSend={() => {}} onBack={() => navigation.navigate('Login')} />
        )}
      </Stack.Screen>

      <Stack.Screen name="ResetPassword">
        {({ navigation }) => (
          <ResetPasswordScreen onReset={() => {}} onBack={() => navigation.navigate('Login')} />
        )}
      </Stack.Screen>

      <Stack.Screen name="ProfileSetup">
        {({ navigation }) => (
          <ProfileSetupScreen
            onComplete={async (data) => {
              try {
                const profile = await authService.updateProfile({ ...data, profileComplete: true });
                updateProfile(profile);
              } catch (error) {
                await logout();
                navigation.navigate('Login');
                throw error;
              }
            }}
          />
        )}
      </Stack.Screen>
    </Stack.Navigator>
  );
}
