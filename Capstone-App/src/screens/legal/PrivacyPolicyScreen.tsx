import { ScrollView, Text, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { ScreenWrapper } from '@/components/shared/ScreenWrapper';
import { Header } from '@/components/shared/Header';
import { layout } from '@/constants/theme';
import { PRIVACY_POLICY, PRIVACY_POLICY_UPDATED } from './privacyPolicy';

export function PrivacyPolicyScreen() {
  const navigation = useNavigation();
  return (
    <ScreenWrapper>
      <Header title="Privacy policy" showBack onBack={() => navigation.goBack()} />
      <ScrollView contentContainerStyle={{ paddingBottom: 48 }}>
        <View className="px-5 pt-6 w-full self-center" style={{ maxWidth: layout.reading }}>
          <Text className="text-text-secondary font-body text-sm mb-6">Last updated {PRIVACY_POLICY_UPDATED}</Text>
          {PRIVACY_POLICY.map((section) => (
            <View key={section.heading} className="mb-6">
              <Text accessibilityRole="header" className="text-text-primary font-display text-xl mb-2">{section.heading}</Text>
              {section.body.map((paragraph) => (
                <Text key={paragraph} className="text-text-secondary font-body text-base leading-6 mb-2">{paragraph}</Text>
              ))}
            </View>
          ))}
        </View>
      </ScrollView>
    </ScreenWrapper>
  );
}
