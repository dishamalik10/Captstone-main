import { api, resolveApiUrl } from './api';
import type { ChatMessage, ClothingCategory, ClothingItem, Occasion, Outfit, Product, SocialPost, User, WardrobeStats, Weather, SellerStats, SellerListing, SellerOrder, WearLog, StyleAnalysis, PurchaseImpact } from '@/types';
import { Platform } from 'react-native';

export interface UploadAsset {
  uri: string;
  fileName?: string | null;
  mimeType?: string | null;
  file?: File;
}

interface ApiPrediction {
  label: string;
  confidence: number;
  top_3: Array<{ label?: string; confidence?: number }>;
}

interface ApiClothingItem {
  item_id: string;
  user_id: string;
  category: 'Top' | 'Bottom' | 'Dress' | 'Footwear' | 'Outerwear' | 'Accessory';
  subcategory: string;
  garment_group: string;
  color_name: string;
  image_url: string;
  confidence: Record<string, ApiPrediction>;
  needs_review: boolean;
  pattern?: string | null;
  seasons: string[];
  available: boolean;
  created_at: string;
}

interface ApiRecommendation {
  recommendation_id: string;
  item_ids: string[];
  items: ApiClothingItem[];
  compatibility_score: number;
  component_scores: Record<string, number>;
  explanation: string;
  analysis?: Record<string, unknown>;
}

const categoryToApp: Record<ApiClothingItem['category'], ClothingCategory> = {
  Top: 'tops',
  Bottom: 'bottoms',
  Dress: 'dresses',
  Footwear: 'shoes',
  Outerwear: 'outerwear',
  Accessory: 'accessories',
};

const categoryToApi: Record<ClothingCategory, ApiClothingItem['category']> = {
  tops: 'Top',
  bottoms: 'Bottom',
  dresses: 'Dress',
  shoes: 'Footwear',
  outerwear: 'Outerwear',
  accessories: 'Accessory',
};

const colorHexes: Record<string, string> = {
  black: '#171717', white: '#F5F5F0', grey: '#808080', gray: '#808080',
  red: '#B83A3A', blue: '#3B68A0', green: '#4F7651', yellow: '#D6B84B',
  brown: '#795548', beige: '#D8C3A5', pink: '#D98CA3', purple: '#76518A',
  orange: '#D8783C', navy: '#1F2D4D', gold: '#C8A96E',
};

function normalizeSeason(seasons: string[]) {
  const value = seasons[0]?.toLowerCase();
  if (value === 'autumn') return 'fall' as const;
  if (value === 'spring' || value === 'summer' || value === 'fall' || value === 'winter') return value;
  return 'all' as const;
}

function mapItem(item: ApiClothingItem): ClothingItem {
  const color = item.color_name || 'Unknown';
  return {
    id: item.item_id,
    name: item.subcategory || item.category,
    category: categoryToApp[item.category],
    color,
    colorHex: colorHexes[color.toLowerCase()] ?? '#8A8A8A',
    pattern: item.pattern || 'Unknown',
    brand: item.garment_group || 'My wardrobe',
    season: normalizeSeason(item.seasons),
    imageUrl: resolveApiUrl(item.image_url),
    wearCount: 0,
    createdAt: item.created_at,
    confidence: item.confidence.product_type?.confidence,
    needsReview: item.needs_review,
    subcategory: item.subcategory,
    garmentGroup: item.garment_group,
  };
}

function mapOutfit(
  recommendation: ApiRecommendation,
  occasion: Occasion,
  slate?: { comparison_explanation?: string; comparison_alternative?: string; comparison_source?: 'local_llm' | 'rules'; evidence_confidence?: 'limited' | 'moderate'; confidence_note?: string; score_disclosure?: string },
): Outfit {
  return {
    id: recommendation.recommendation_id,
    name: `${occasion[0].toUpperCase()}${occasion.slice(1)} Look`,
    occasion,
    compatibilityScore: recommendation.compatibility_score,
    imageUrl: recommendation.items[0]
      ? resolveApiUrl(recommendation.items[0].image_url)
      : '',
    itemIds: recommendation.item_ids,
    explanation: recommendation.explanation,
    componentScores: recommendation.component_scores,
    comparisonExplanation: slate?.comparison_explanation,
    comparisonAlternative: slate?.comparison_alternative,
    comparisonSource: slate?.comparison_source,
    evidenceConfidence: slate?.evidence_confidence,
    confidenceNote: slate?.confidence_note,
    scoreDisclosure: slate?.score_disclosure,
  };
}

export const authService = {
  async login(email: string, password: string) {
    const { data } = await api.post<{ user: User; token: string }>('/auth/login', { email, password });
    return data;
  },
  async signup(data: { fullName: string; email: string; password?: string }) {
    const response = await api.post<{ user: User; token: string }>('/auth/signup', {
      full_name: data.fullName,
      email: data.email,
      password: data.password,
    });
    return response.data;
  },
  async me() {
    return (await api.get<User>('/auth/me')).data;
  },
  async logout() {
    await api.post('/auth/logout');
  },
  async updateProfile(data: Partial<User>) {
    return (await api.patch<User>('/users/me', data)).data;
  },
};

export const wardrobeService = {
  async getItems(userId: string): Promise<ClothingItem[]> {
    const { data } = await api.get<ApiClothingItem[]>(`/wardrobe/${encodeURIComponent(userId)}`);
    return data.filter((item) => item.available).map(mapItem);
  },
  async upload(userId: string, asset: UploadAsset): Promise<ClothingItem> {
    const form = new FormData();
    form.append('user_id', userId);
    const name = asset.fileName || `wardrobe-${Date.now()}.jpg`;
    if (Platform.OS === 'web') {
      const blob = asset.file ?? await (await fetch(asset.uri)).blob();
      form.append('file', blob, name);
    } else {
      form.append('file', {
        uri: asset.uri,
        name,
        type: asset.mimeType || 'image/jpeg',
      } as unknown as Blob);
    }
    const { data } = await api.post<ApiClothingItem>('/wardrobe/upload', form);
    return mapItem(data);
  },
  async updateItem(userId: string, id: string, data: Partial<ClothingItem>): Promise<ClothingItem> {
    const payload: Record<string, unknown> = {};
    if (data.category) payload.category = categoryToApi[data.category];
    if (data.name) payload.subcategory = data.name;
    if (data.color) payload.color_name = data.color;
    if (data.pattern) payload.pattern = data.pattern;
    if (data.season) payload.seasons = data.season === 'all' ? [] : [data.season === 'fall' ? 'Autumn' : data.season];
    const response = await api.patch<ApiClothingItem>(
      `/wardrobe/${encodeURIComponent(userId)}/${encodeURIComponent(id)}`,
      payload,
    );
    return mapItem(response.data);
  },
  async deleteItem(userId: string, id: string) {
    await api.delete(`/wardrobe/${encodeURIComponent(userId)}/${encodeURIComponent(id)}`);
    return { id };
  },
  async getStats(userId: string): Promise<WardrobeStats> {
    const items = await this.getItems(userId);
    return {
      totalItems: items.length,
      mostWorn: { name: items[0]?.name ?? 'None', count: items[0]?.wearCount ?? 0 },
      leastWorn: { name: items.at(-1)?.name ?? 'None', count: items.at(-1)?.wearCount ?? 0 },
    };
  },
  async getStyleAnalysis(): Promise<StyleAnalysis> {
    return (await api.get<StyleAnalysis>('/wardrobe/style-analysis')).data;
  },
  async analyzePurchase(asset: UploadAsset): Promise<PurchaseImpact> {
    const form = new FormData();
    const name = asset.fileName || `purchase-${Date.now()}.jpg`;
    if (Platform.OS === 'web') {
      const blob = asset.file ?? await (await fetch(asset.uri)).blob();
      form.append('file', blob, name);
    } else {
      form.append('file', {
        uri: asset.uri,
        name,
        type: asset.mimeType || 'image/jpeg',
      } as unknown as Blob);
    }
    return (await api.post<PurchaseImpact>('/wardrobe/purchase-impact', form)).data;
  },
};

export const outfitService = {
  async getRecommendations(
    userId: string,
    occasion: Occasion = 'casual',
    options?: { city?: string; temperature?: number; condition?: string },
    excludeRecommendationIds: string[] = [],
  ): Promise<Outfit[]> {
    const { data } = await api.post<{
      recommendations: ApiRecommendation[];
      comparison_explanation?: string;
      comparison_alternative?: string;
      comparison_source?: 'local_llm' | 'rules';
      evidence_confidence?: 'limited' | 'moderate';
      confidence_note?: string;
      score_disclosure?: string;
    }>('/recommend', {
      user_id: userId,
      occasion,
      mood: 'Confident',
      city: options?.city,
      temperature_c: options?.temperature,
      condition: options?.condition,
      limit: 5,
      exclude_recommendation_ids: excludeRecommendationIds,
    });
    const alternative = data.recommendations[1];
    const comparison_alternative = alternative?.items
      .map((item) => `${item.color_name} ${item.subcategory}`)
      .join(' · ');
    return data.recommendations.map((item) => mapOutfit(item, occasion, { ...data, comparison_alternative }));
  },
  async feedback(userId: string, outfit: Outfit, action: 'skip' | 'like' | 'dislike' | 'save' | 'wear') {
    const { data } = await api.post('/feedback', {
      user_id: userId,
      recommendation_id: outfit.id,
      item_ids: outfit.itemIds,
      action,
    });
    return data;
  },
};

export const marketplaceService = {
  async getProducts() {
    return (await api.get<Product[]>('/marketplace/products')).data;
  },
  async getProduct(id: string) {
    return (await api.get<Product>(`/marketplace/products/${encodeURIComponent(id)}`)).data;
  },
  async getSellerStats() {
    return (await api.get<{ stats: SellerStats }>('/marketplace/seller')).data.stats;
  },
  async getSellerListings() {
    return (await api.get<{ listings: SellerListing[] }>('/marketplace/seller')).data.listings;
  },
  async getSellerOrders() {
    return (await api.get<{ orders: SellerOrder[] }>('/marketplace/seller')).data.orders;
  },
  async placeOrder(productIds: string[]) {
    return (await api.post('/marketplace/orders', { product_ids: productIds })).data;
  },
};

export const chatService = {
  async getMessages(sessionId: string) {
    const messages = (await api.get<ChatMessage[]>('/chat/messages', {
      params: { session_id: sessionId },
    })).data;
    return messages.map((message) => message.outfit
      ? { ...message, outfit: { ...message.outfit, imageUrl: resolveApiUrl(message.outfit.imageUrl) } }
      : message);
  },
  async sendMessage(content: string, sessionId: string) {
    const message = (await api.post<ChatMessage>('/chat/messages', {
      content,
      session_id: sessionId,
    })).data;
    return message.outfit
      ? { ...message, outfit: { ...message.outfit, imageUrl: resolveApiUrl(message.outfit.imageUrl) } }
      : message;
  },
};

export const socialService = {
  async getFeed() {
    return (await api.get<SocialPost[]>('/social/feed')).data;
  },
  async getUser(id: string) {
    return (await api.get<User>(`/users/${encodeURIComponent(id)}`)).data;
  },
  async toggleLike(id: string) {
    return (await api.post<{ liked: boolean }>(`/social/posts/${encodeURIComponent(id)}/like`)).data;
  },
  async toggleFollow(id: string) {
    return (await api.post<{ following: boolean }>(`/social/users/${encodeURIComponent(id)}/follow`)).data;
  },
};

export const weatherService = {
  async getCurrent(city: string) {
    return (await api.get<Weather>('/weather', { params: { city } })).data;
  },
};

export const activityService = {
  async getWearLogs() {
    return (await api.get<WearLog[]>('/activity/wear-logs')).data;
  },
};
