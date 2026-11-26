import { useState } from 'react';
import { View, Text, ScrollView, Pressable, Switch } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { ScreenWrapper } from '@/components/shared/ScreenWrapper';
import { Header } from '@/components/shared/Header';
import { EmptyState } from '@/components/shared/EmptyState';
import { Avatar } from '@/components/ui/Avatar';
import { Modal } from '@/components/ui/Modal';
import { useAuthStore } from '@/store/authStore';
import { hapticLight } from '@/utils/haptics';
import { cn } from '@/utils/helpers';
import { useAppearanceStore } from '@/store/appearanceStore';
import { useThemeColors } from '@/hooks/useThemeColors';
import { useWearLogs } from '@/hooks';
import { layout } from '@/constants/theme';

type Section = { id: string; label: string; icon: keyof typeof Ionicons.glyphMap; route: string };

const SECTIONS: Section[] = [
  { id: 'edit', label: 'Edit Profile', icon: 'person-outline', route: 'EditProfile' },
  { id: 'style', label: 'Style Preferences', icon: 'color-palette-outline', route: 'StylePreferences' },
  { id: 'analysis', label: 'Style Analyzer', icon: 'analytics-outline', route: 'StyleAnalysis' },
  { id: 'virtual', label: 'My Virtual Look', icon: 'person-circle-outline', route: 'VirtualLook' },
  { id: 'body', label: 'Body & Sizing', icon: 'body-outline', route: 'BodySizing' },
  { id: 'skin', label: 'Skin Tone', icon: 'sunny-outline', route: 'SkinTone' },
  { id: 'notifications', label: 'Notification Settings', icon: 'notifications-outline', route: 'NotificationSettings' },
  { id: 'marketplace', label: 'Marketplace', icon: 'bag-handle-outline', route: 'Marketplace' },
  { id: 'seller', label: 'Seller Dashboard', icon: 'storefront-outline', route: 'SellerDashboard' },
  { id: 'orders', label: 'My Orders', icon: 'receipt-outline', route: 'MyOrders' },
  { id: 'messages', label: 'Messages', icon: 'chatbubbles-outline', route: 'Messages' },
  { id: 'chat', label: 'AI Chat', icon: 'chatbubble-outline', route: 'Chat' },
  { id: 'activity', label: 'Activity History', icon: 'time-outline', route: 'ActivityHistory' },
  { id: 'donate', label: 'Donate Unworn Clothes', icon: 'heart-outline', route: 'Donate' },
  { id: 'appearance', label: 'Appearance', icon: 'moon-outline', route: 'Appearance' },
  { id: 'help', label: 'Help & Support', icon: 'help-circle-outline', route: 'HelpSupport' },
];

const GROUPS: { title: string; ids: string[] }[] = [
  { title: 'Your style', ids: ['edit', 'virtual', 'style', 'analysis', 'body', 'skin'] },
  { title: 'Activity', ids: ['chat', 'activity', 'donate'] },
  { title: 'Buy and sell', ids: ['marketplace', 'seller', 'orders', 'messages'] },
  { title: 'Settings', ids: ['notifications', 'appearance', 'help'] },
];

export function ProfileScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<Record<string, object | undefined>>>();
  const palette = useThemeColors();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const [showLogout, setShowLogout] = useState(false);

  return (
    <ScreenWrapper>
      <ScrollView className="flex-1" contentContainerStyle={{ paddingBottom: 120 }} showsVerticalScrollIndicator={false}>
        <View className="w-full self-center" style={{ maxWidth: layout.reading }}>
          <View className="px-5 pt-6 pb-8">
            <View className="flex-row items-center gap-5">
              <Avatar uri={user?.avatarUrl} name={user?.fullName} size="xl" />
              <View className="flex-1">
                <Text accessibilityRole="header" className="text-text-primary font-display text-3xl" numberOfLines={2}>
                  {user?.fullName}
                </Text>
                {!!user?.location && (
                  <View className="flex-row items-center gap-1 mt-1">
                    <Ionicons name="location-outline" size={14} color={palette.textSecondary} />
                    <Text className="text-text-secondary font-body text-sm">{user.location}</Text>
                  </View>
                )}
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel="Edit profile"
                  onPress={() => navigation.navigate('EditProfile')}
                  className="self-start mt-3 h-9 px-4 rounded-full border border-border-strong items-center justify-center hover:bg-surface-raised"
                >
                  <Text className="text-text-primary font-body-medium text-sm">Edit profile</Text>
                </Pressable>
              </View>
            </View>
            <View className="flex-row mt-8 border-y border-border">
              <Stat value={user?.itemsCount ?? 0} label="Pieces" />
              <Stat value={user?.outfitsSaved ?? 0} label="Outfits saved" divider />
              <Stat value={user?.following ?? 0} label="Following" divider />
            </View>
          </View>

          {GROUPS.map((group) => (
            <View key={group.title} className="px-5 mb-10">
              <Text accessibilityRole="header" className="text-text-primary font-display text-xl mb-3">{group.title}</Text>
              <View className="border-t border-text-primary">
                {group.ids.map((id, i) => {
                  const s = SECTIONS.find((x) => x.id === id)!;
                  return (
                    <Pressable
                      key={s.id}
                      accessibilityRole="button"
                      accessibilityLabel={s.label}
                      onPress={() => {
                        hapticLight();
                        navigation.navigate(s.route);
                      }}
                      className="flex-row items-center min-h-14 border-b border-border hover:bg-surface-raised"
                    >
                      <Ionicons name={s.icon} size={20} color={palette.textSecondary} />
                      <Text className="text-text-primary font-body text-base ml-4 flex-1">{prettyLabel(s.label)}</Text>
                      <Ionicons name="chevron-forward" size={16} color={palette.textTertiary} />
                    </Pressable>
                  );
                })}
              </View>
            </View>
          ))}

          <View className="px-5">
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Log out"
              onPress={() => setShowLogout(true)}
              className="flex-row items-center justify-center gap-2 min-h-12 rounded-sm border border-destructive hover:bg-surface-raised"
            >
              <Ionicons name="log-out-outline" size={19} color={palette.destructive} />
              <Text className="text-destructive font-body-medium text-base">Log out</Text>
            </Pressable>
          </View>
        </View>
      </ScrollView>

      <Modal
        visible={showLogout}
        onClose={() => setShowLogout(false)}
        title="Log out of AURA?"
        message="Your wardrobe stays saved. You can log back in anytime."
        confirmLabel="Log out"
        onConfirm={logout}
        destructive
      />
    </ScreenWrapper>
  );
}

/** Sentence case for display; the accessibility labels keep their original wording. */
const DISPLAY: Record<string, string> = {
  'AI Chat': 'Stylist chat',
  'Body & Sizing': 'Body and sizing',
  'My Virtual Look': 'My virtual look',
};
function prettyLabel(label: string) {
  return DISPLAY[label] ?? label.charAt(0) + label.slice(1).toLowerCase();
}

function Stat({ value, label, divider }: { value: number; label: string; divider?: boolean }) {
  return (
    <View className={cn('flex-1 py-4', divider ? 'pl-4 border-l border-border' : 'pr-4')}>
      <Text className="text-text-primary font-display text-2xl tabular-nums">{value}</Text>
      <Text className="text-text-secondary font-body text-xs mt-0.5">{label}</Text>
    </View>
  );
}

export function SettingsScreen({ title, children }: { title: string; children: React.ReactNode }) {
  const navigation = useNavigation();
  return (
    <ScreenWrapper>
      <Header title={title} showBack onBack={() => navigation.goBack()} />
      <ScrollView contentContainerStyle={{ paddingBottom: 48 }}>
        <View className="px-5 pt-6 w-full self-center" style={{ maxWidth: layout.reading }}>
          {children}
        </View>
      </ScrollView>
    </ScreenWrapper>
  );
}

export function NotificationSettingsScreen() {
  const [push, setPush] = useState(true);
  const [outfits, setOutfits] = useState(true);
  const [marketplace, setMarketplace] = useState(false);

  return (
    <SettingsScreen title="Notifications">
      <View className="border-t border-text-primary">
        <SettingToggle label="Push notifications" hint="Allow AURA to notify you" value={push} onChange={setPush} />
        <SettingToggle label="Outfit recommendations" hint="A suggestion for the day ahead" value={outfits} onChange={setOutfits} divider />
        <SettingToggle label="Marketplace updates" hint="Messages and order changes" value={marketplace} onChange={setMarketplace} divider />
      </View>
    </SettingsScreen>
  );
}

const APPEARANCE_OPTIONS = [
  { key: 'dark', label: 'Dark', icon: 'moon-outline', hint: 'Warm charcoal, easy at night' },
  { key: 'light', label: 'Light', icon: 'sunny-outline', hint: 'Ivory paper, bright and clear' },
  { key: 'system', label: 'System', icon: 'phone-portrait-outline', hint: 'Follows your device setting' },
] as const;

export function AppearanceScreen() {
  const theme = useAppearanceStore((state) => state.mode);
  const setTheme = useAppearanceStore((state) => state.setMode);
  const palette = useThemeColors();
  return (
    <SettingsScreen title="Appearance">
      <View className="border-t border-text-primary" accessibilityRole="radiogroup">
        {APPEARANCE_OPTIONS.map((t) => {
          const selected = theme === t.key;
          return (
            <Pressable
              key={t.key}
              accessibilityRole="radio"
              accessibilityState={{ checked: selected }}
              accessibilityLabel={t.label}
              onPress={() => {
                hapticLight();
                setTheme(t.key);
              }}
              className="flex-row items-center min-h-16 py-3 border-b border-border hover:bg-surface-raised"
            >
              <View className={cn('w-10 h-10 rounded-full border items-center justify-center', selected ? 'border-primary bg-primary' : 'border-border bg-surface')}>
                <Ionicons name={t.icon} size={18} color={selected ? palette.primaryInk : palette.textSecondary} />
              </View>
              <View className="flex-1 ml-4">
                <Text className="text-text-primary font-body-medium text-base">{t.label}</Text>
                <Text className="text-text-secondary font-body text-sm">{t.hint}</Text>
              </View>
              <View className={cn('w-5 h-5 rounded-full border items-center justify-center', selected ? 'border-primary' : 'border-border-strong')}>
                {selected && <View className="w-2.5 h-2.5 rounded-full bg-primary" />}
              </View>
            </Pressable>
          );
        })}
      </View>
    </SettingsScreen>
  );
}

export function ActivityHistoryScreen() {
  const { data: logs, isLoading } = useWearLogs();

  if (isLoading) return <ScreenWrapper loading />;

  return (
    <SettingsScreen title="Activity history">
      {logs?.length ? (
        <View className="border-t border-text-primary">
          {logs.map((log: { id: string; outfitName: string; date: string }) => (
            <View key={log.id} className="py-4 border-b border-border flex-row justify-between items-center">
              <Text className="text-text-primary font-body text-base flex-1 pr-3">{log.outfitName}</Text>
              <Text className="text-text-secondary font-body text-sm tabular-nums">{log.date}</Text>
            </View>
          ))}
        </View>
      ) : (
        <View className="min-h-[420px]">
          <EmptyState
            icon="time-outline"
            title="Nothing worn yet"
            message="When you mark an outfit as worn today, it appears here."
          />
        </View>
      )}
    </SettingsScreen>
  );
}

export function HelpSupportScreen() {
  const palette = useThemeColors();
  return (
    <SettingsScreen title="Help and support">
      <Text className="text-text-primary font-display text-2xl mb-3">How can we help?</Text>
      <Text className="text-text-secondary font-body text-base leading-6 mb-6">
        Questions about your wardrobe, outfits or account? Write to the support team or read the FAQ.
      </Text>
      <View className="border-t border-text-primary">
        <View className="flex-row items-center gap-3 min-h-14 border-b border-border">
          <Ionicons name="mail-outline" size={20} color={palette.textPrimary} />
          <Text selectable className="text-text-primary font-body-medium text-base">support@wearbefore.com</Text>
        </View>
        <View className="flex-row items-center gap-3 min-h-14 border-b border-border">
          <Ionicons name="help-circle-outline" size={20} color={palette.textPrimary} />
          <Text selectable className="text-text-primary font-body-medium text-base">wearbefore.com/help</Text>
        </View>
      </View>
    </SettingsScreen>
  );
}

function SettingToggle({
  label,
  hint,
  value,
  onChange,
  divider,
}: {
  label: string;
  hint?: string;
  value: boolean;
  onChange: (v: boolean) => void;
  divider?: boolean;
}) {
  const palette = useThemeColors();
  return (
    <View className={cn('flex-row items-center justify-between min-h-16 py-3 border-b border-border', divider && '')}>
      <View className="flex-1 pr-4">
        <Text className="text-text-primary font-body text-base">{label}</Text>
        {hint ? <Text className="text-text-secondary font-body text-sm">{hint}</Text> : null}
      </View>
      <Switch
        accessibilityLabel={label}
        value={value}
        onValueChange={onChange}
        trackColor={{ true: palette.accent, false: palette.border }}
        thumbColor={palette.surface}
        ios_backgroundColor={palette.border}
      />
    </View>
  );
}
