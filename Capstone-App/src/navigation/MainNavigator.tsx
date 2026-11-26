import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { TabBar } from '@/components/shared/TabBar';
import { HomeScreen } from '@/screens/home/HomeScreen';
import { WardrobeScreen } from '@/screens/wardrobe/WardrobeScreen';
import { ClothingDetailScreen } from '@/screens/wardrobe/ClothingDetailScreen';
import { DonateScreen } from '@/screens/wardrobe/DonateScreen';
import { AIStylistScreen } from '@/screens/outfits/AIStylistScreen';
import { OutfitBuilderScreen } from '@/screens/outfits/OutfitBuilderScreen';
import { VirtualLookScreen } from '@/screens/outfits/VirtualLookScreen';
import type { Occasion } from '@/types';
import { ChatScreen } from '@/screens/chat/ChatScreen';
import { ProductDetailScreen } from '@/screens/marketplace/ProductDetailScreen';
import { CartScreen } from '@/screens/marketplace/CartScreen';
import { CheckoutScreen } from '@/screens/marketplace/CheckoutScreen';
import { SellerDashboardScreen } from '@/screens/marketplace/SellerDashboardScreen';
import { MarketplaceScreen } from '@/screens/marketplace/MarketplaceScreen';
import { SellItemScreen } from '@/screens/marketplace/SellItemScreen';
import { MyOrdersScreen } from '@/screens/marketplace/MyOrdersScreen';
import { MessagesScreen } from '@/screens/marketplace/MessagesScreen';
import { ConversationScreen } from '@/screens/marketplace/ConversationScreen';
import { SocialFeedScreen } from '@/screens/social/SocialFeedScreen';
import { UserProfileScreen } from '@/screens/social/UserProfileScreen';
import {
  ProfileScreen,
  NotificationSettingsScreen,
  AppearanceScreen,
  ActivityHistoryScreen,
  HelpSupportScreen,
} from '@/screens/settings/ProfileScreen';
import { ProfileSetupScreen } from '@/screens/onboarding/ProfileSetupScreen';
import { StyleAnalysisScreen } from '@/screens/settings/StyleAnalysisScreen';
import { useAuthStore } from '@/store/authStore';
import { useNavigation } from '@react-navigation/native';
import { authService } from '@/services';
import { useThemeColors } from '@/hooks/useThemeColors';
import { useRealtime } from '@/hooks/useRealtime';

export type MainStackParamList = {
  Tabs: undefined;
  ClothingDetail: { id: string };
  Donate: undefined;
  OutfitBuilder: undefined;
  VirtualLook: { occasion?: Occasion; outfitId?: string } | undefined;
  Chat: undefined;
  ProductDetail: { id: string };
  Cart: undefined;
  Checkout: undefined;
  SellerDashboard: undefined;
  Marketplace: undefined;
  SellItem: undefined;
  MyOrders: undefined;
  Messages: undefined;
  Conversation: { id: string };
  SocialFeed: undefined;
  UserProfile: { userId: string };
  EditProfile: undefined;
  StylePreferences: undefined;
  StyleAnalysis: undefined;
  BodySizing: undefined;
  SkinTone: undefined;
  NotificationSettings: undefined;
  ActivityHistory: undefined;
  Appearance: undefined;
  HelpSupport: undefined;
};

const Tab = createBottomTabNavigator();
const Stack = createNativeStackNavigator<MainStackParamList>();

function TabNavigator() {
  const palette = useThemeColors();
  return (
    <Tab.Navigator
      tabBar={(props) => <TabBar {...props} />}
      screenOptions={{ headerShown: false, sceneStyle: { backgroundColor: palette.background } }}
    >
      <Tab.Screen name="Home" component={HomeScreen} />
      <Tab.Screen name="Wardrobe" component={WardrobeScreen} />
      <Tab.Screen name="AIStylist" component={AIStylistScreen} />
      <Tab.Screen name="AIChat" component={ChatScreen} />
      <Tab.Screen name="Profile" component={ProfileScreen} />
    </Tab.Navigator>
  );
}

function EditProfileScreen() {
  const updateProfile = useAuthStore((s) => s.updateProfile);
  const user = useAuthStore((s) => s.user);
  const navigation = useNavigation();
  return (
    <ProfileSetupScreen
      completeLabel="Save Changes"
      onBack={() => navigation.goBack()}
      initialData={user ?? undefined}
      onComplete={async (data) => {
        const saved = await authService.updateProfile({
          ...data,
          profileComplete: true,
        });
        updateProfile(saved);
        navigation.goBack();
      }}
    />
  );
}

export function MainNavigator() {
  const palette = useThemeColors();
  useRealtime(); // live chat, presence and order updates while signed in
  return (
    <Stack.Navigator
      initialRouteName="Tabs"
      screenOptions={{ headerShown: false, animation: 'slide_from_right', contentStyle: { backgroundColor: palette.background } }}
    >
      <Stack.Screen name="Tabs" component={TabNavigator} />
      <Stack.Screen name="ClothingDetail" component={ClothingDetailScreen} />
      <Stack.Screen name="Donate" component={DonateScreen} />
      <Stack.Screen name="OutfitBuilder" component={OutfitBuilderScreen} />
      <Stack.Screen name="VirtualLook" component={VirtualLookScreen} />
      <Stack.Screen name="Chat" component={ChatScreen} />
      <Stack.Screen name="ProductDetail" component={ProductDetailScreen} />
      <Stack.Screen name="Cart" component={CartScreen} />
      <Stack.Screen name="Checkout" component={CheckoutScreen} />
      <Stack.Screen name="SellerDashboard" component={SellerDashboardScreen} />
      <Stack.Screen name="Marketplace" component={MarketplaceScreen} />
      <Stack.Screen name="SellItem" component={SellItemScreen} />
      <Stack.Screen name="MyOrders" component={MyOrdersScreen} />
      <Stack.Screen name="Messages" component={MessagesScreen} />
      <Stack.Screen name="Conversation" component={ConversationScreen} />
      <Stack.Screen name="SocialFeed" component={SocialFeedScreen} />
      <Stack.Screen name="UserProfile" component={UserProfileScreen} />
      <Stack.Screen name="EditProfile" component={EditProfileScreen} />
      <Stack.Screen name="StylePreferences" component={EditProfileScreen} />
      <Stack.Screen name="StyleAnalysis" component={StyleAnalysisScreen} />
      <Stack.Screen name="BodySizing" component={EditProfileScreen} />
      <Stack.Screen name="SkinTone" component={EditProfileScreen} />
      <Stack.Screen name="NotificationSettings" component={NotificationSettingsScreen} />
      <Stack.Screen name="ActivityHistory" component={ActivityHistoryScreen} />
      <Stack.Screen name="Appearance" component={AppearanceScreen} />
      <Stack.Screen name="HelpSupport" component={HelpSupportScreen} />
    </Stack.Navigator>
  );
}
