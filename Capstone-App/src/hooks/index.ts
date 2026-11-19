import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { authService, wardrobeService, outfitService, marketplaceService, weatherService, socialService, activityService } from '@/services';
import { useAuthStore } from '@/store/authStore';
import type { Occasion, Outfit } from '@/types';

const FALLBACK_USER_ID = 'demo-user';

export function useWeather() {
  const city = useAuthStore((state) => state.user?.location);
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
  const { data: weather } = useWeather();
  return useQuery({
    queryKey: ['outfits', userId, occasion, weather?.temperature, weather?.condition],
    queryFn: () => outfitService.getRecommendations(userId, occasion, {
      city: user?.location,
      temperature: weather?.temperature,
      condition: weather?.condition,
    }),
  });
}

export function useProducts() {
  return useQuery({ queryKey: ['products'], queryFn: () => marketplaceService.getProducts() });
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
  const feedbackMutation = useMutation({
    mutationFn: ({ outfit, action }: { outfit: Outfit; action: 'skip' | 'like' | 'dislike' | 'save' | 'wear' }) =>
      outfitService.feedback(userId, outfit, action),
  });
  const alternativesMutation = useMutation({
    mutationFn: ({ occasion, excludeRecommendationIds, temperature, condition }: {
      occasion: Occasion;
      excludeRecommendationIds: string[];
      temperature?: number;
      condition?: string;
    }) => outfitService.getRecommendations(userId, occasion, {
      city: user?.location,
      temperature,
      condition,
    }, excludeRecommendationIds),
  });
  return { feedbackMutation, alternativesMutation };
}
