import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { authService, wardrobeService, outfitService, marketplaceService, weatherService, socialService, activityService, donationService } from '@/services';
import { useAuthStore } from '@/store/authStore';
import { useLocationStore } from '@/store/locationStore';
import { useRealtimeStore } from '@/store/realtimeStore';
import type { Occasion, Outfit } from '@/types';

const FALLBACK_USER_ID = 'demo-user';

/** The city used for live weather: the one typed on the Stylist screen, else the profile city. */
export function useStylingCity() {
  const override = useLocationStore((state) => state.city);
  const profileCity = useAuthStore((state) => state.user?.location);
  return override || profileCity || undefined;
}

export function useWeather() {
  const city = useStylingCity();
  return useQuery({
    queryKey: ['weather', city],
    queryFn: () => weatherService.getCurrent(city!),
    enabled: Boolean(city),
    retry: false,
  });
}

export function useWardrobeItems() {
  const userId = useAuthStore((state) => state.user?.id) ?? FALLBACK_USER_ID;
  return useQuery({
    queryKey: ['wardrobe', userId],
    queryFn: () => wardrobeService.getItems(userId),
  });
}

export function useWardrobeStats() {
  const userId = useAuthStore((state) => state.user?.id) ?? FALLBACK_USER_ID;
  return useQuery({
    queryKey: ['wardrobe-stats', userId],
    queryFn: () => wardrobeService.getStats(userId),
  });
}

export function useStyleAnalysis() {
  const userId = useAuthStore((state) => state.user?.id) ?? FALLBACK_USER_ID;
  return useQuery({
    queryKey: ['style-analysis', userId],
    queryFn: () => wardrobeService.getStyleAnalysis(),
  });
}

export function useOutfitRecommendations(occasion: Occasion = 'casual') {
  const user = useAuthStore((state) => state.user);
  const userId = user?.id ?? FALLBACK_USER_ID;
  const city = useStylingCity();
  const { data: weather, isFetching: weatherFetching } = useWeather();
  return useQuery({
    queryKey: ['outfits', userId, occasion, city, weather?.temperature, weather?.condition],
    // Wait for live weather so outfits are ranked for the right season, not a placeholder.
    enabled: !weatherFetching,
    queryFn: () => outfitService.getRecommendations(userId, occasion, {
      city,
      temperature: weather?.temperature,
      condition: weather?.condition,
    }),
  });
}

export function useProducts() {
  return useQuery({ queryKey: ['products'], queryFn: () => marketplaceService.getProducts() });
}

export function useSellerDashboard() {
  return useQuery({ queryKey: ['seller-dashboard'], queryFn: () => marketplaceService.getDashboard(), staleTime: 0 });
}

export function useMyOrders() {
  return useQuery({ queryKey: ['my-orders'], queryFn: () => marketplaceService.getMyOrders(), staleTime: 0 });
}

/** Marketplace inbox. Updates arrive over the WebSocket; polling only while it is down. */
export function useConversations() {
  const signedIn = useAuthStore((state) => Boolean(state.user?.id));
  const live = useRealtimeStore((state) => state.connected);
  return useQuery({
    queryKey: ['conversations'],
    queryFn: () => marketplaceService.getConversations(),
    enabled: signedIn,
    refetchInterval: live ? false : 8000,
    staleTime: 0,
  });
}

export function useConversation(id: string) {
  const live = useRealtimeStore((state) => state.connected);
  return useQuery({
    queryKey: ['conversation', id],
    queryFn: () => marketplaceService.getConversation(id),
    refetchInterval: live ? false : 5000,
    staleTime: 0,
  });
}

/** Refresh every marketplace view after a listing, order or message changes. */
export function useRefreshMarketplace() {
  const queryClient = useQueryClient();
  return () => {
    for (const key of ['products', 'product', 'seller-dashboard', 'my-orders', 'conversations']) {
      void queryClient.invalidateQueries({ queryKey: [key] });
    }
  };
}

export function useProduct(id: string) {
  return useQuery({
    queryKey: ['product', id],
    queryFn: () => marketplaceService.getProduct(id),
    enabled: !!id,
  });
}

export function useSocialFeed() {
  return useQuery({ queryKey: ['social-feed'], queryFn: () => socialService.getFeed() });
}

export function useDonationCandidates(minDays: number) {
  const userId = useAuthStore((state) => state.user?.id) ?? FALLBACK_USER_ID;
  return useQuery({
    queryKey: ['donations', userId, minDays],
    queryFn: () => donationService.getCandidates(minDays),
  });
}

export function useDonateItems() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (itemIds: string[]) => donationService.donate(itemIds),
    onSuccess: () => {
      // Donated items leave the wardrobe, its stats and future outfit suggestions.
      for (const key of ['donations', 'wardrobe', 'wardrobe-stats', 'outfits', 'style-analysis']) {
        void queryClient.invalidateQueries({ queryKey: [key] });
      }
    },
  });
}

export function useLogWorn() {
  const userId = useAuthStore((state) => state.user?.id) ?? FALLBACK_USER_ID;
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (itemIds: string[]) => outfitService.logWorn(userId, itemIds),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['donations'] });
      void queryClient.invalidateQueries({ queryKey: ['wear-logs'] });
    },
  });
}

export function useWearLogs() {
  return useQuery({ queryKey: ['wear-logs'], queryFn: () => activityService.getWearLogs() });
}

export function useAuth() {
  const store = useAuthStore();
  const queryClient = useQueryClient();

  const loginMutation = useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      authService.login(email, password),
    onSuccess: async (data) => {
      await store.login(data.user, data.token);
      queryClient.invalidateQueries();
    },
  });

  const signupMutation = useMutation({
    mutationFn: (data: { fullName: string; email: string; password: string }) =>
      authService.signup(data),
    onSuccess: async (data) => {
      await store.login(data.user, data.token);
    },
  });

  return { ...store, loginMutation, signupMutation };
}

export function useOutfitAI() {
  const user = useAuthStore((state) => state.user);
  const userId = user?.id ?? FALLBACK_USER_ID;
  const city = useStylingCity();
  const queryClient = useQueryClient();
  const feedbackMutation = useMutation({
    mutationFn: ({ outfit, action }: { outfit: Outfit; action: 'skip' | 'like' | 'dislike' | 'save' | 'wear' }) =>
      outfitService.feedback(userId, outfit, action),
    onSuccess: (_data, { action }) => {
      if (action !== 'wear') return;
      // Worn pieces leave the never-worn (donation) list and join the activity history.
      void queryClient.invalidateQueries({ queryKey: ['donations'] });
      void queryClient.invalidateQueries({ queryKey: ['wear-logs'] });
    },
  });
  const alternativesMutation = useMutation({
    mutationFn: ({ occasion, excludeRecommendationIds, temperature, condition }: {
      occasion: Occasion;
      excludeRecommendationIds: string[];
      temperature?: number;
      condition?: string;
    }) => outfitService.getRecommendations(userId, occasion, {
      city,
      temperature,
      condition,
    }, excludeRecommendationIds),
  });
  return { feedbackMutation, alternativesMutation };
}
