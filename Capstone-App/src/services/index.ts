import { api, BASE_URL, resolveApiUrl } from './api';
import type { BodyMeasurements, FitAdvice, GarmentSize, MeasurementZone } from '@/types';
import type { ChatMessage, ClothingCategory, ClothingItem, DonationCandidate, Occasion, Outfit, Product, SocialPost, User, WardrobeStats, Weather, SellerDashboard, MarketOrder, Conversation, MarketMessage, ShippingAddress, PaymentMethod, ProductCondition, WearLog, StyleAnalysis, PurchaseImpact, AvatarView, BodyAnalysis, TryOnRender, TryOnStatus, VirtualAvatar } from '@/types';
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
  season_label?: 'Summer' | 'Winter' | 'All-season';
  days_in_wardrobe?: number | null;
  source_url?: string | null;
  source_title?: string | null;
  garment_cutout?: boolean;
  available: boolean;
  size?: GarmentSize | null;
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

function normalizeSeason(seasons: string[], label?: ApiClothingItem['season_label']) {
  // The backend classifies every item as Summer, Winter or All-season.
  if (label === 'Summer') return 'summer' as const;
  if (label === 'Winter') return 'winter' as const;
  if (label === 'All-season' || seasons.length > 1) return 'all' as const;
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
    season: normalizeSeason(item.seasons, item.season_label),
    imageUrl: resolveApiUrl(item.image_url),
    wearCount: 0,
    createdAt: item.created_at,
    confidence: item.confidence.product_type?.confidence,
    needsReview: item.needs_review,
    subcategory: item.subcategory,
    garmentGroup: item.garment_group,
    sourceUrl: item.source_url ?? undefined,
    sourceTitle: item.source_title ?? undefined,
    garmentCutout: item.garment_cutout ?? false,
    size: item.size ?? null,
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
    itemImages: recommendation.items.map((item) => ({
      url: resolveApiUrl(item.image_url),
      label: `${item.color_name} ${item.subcategory}`,
      id: item.item_id,
    })),
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

/** Profile photos AURA stored, e.g. /marketplace/images/<32 hex>.jpg (4.8). */
const STORED_PHOTO = /^\/marketplace\/images\/[0-9a-f]{32}\.(jpg|png|webp)$/;

function stripBase(url: string): string {
  return url.startsWith(BASE_URL) ? url.slice(BASE_URL.length) : url;
}

async function uploadProfilePhoto(uri: string): Promise<User> {
  const form = new FormData();
  const name = `profile-${Date.now()}.jpg`;
  if (Platform.OS === 'web') {
    form.append('file', await (await fetch(uri)).blob(), name);
  } else {
    form.append('file', { uri, name, type: 'image/jpeg' } as unknown as Blob);
  }
  return (await api.post<User>('/users/me/photo', form)).data;
}

/** Web sessions are 7 days (token in localStorage), app sessions 30 (secure store). */
const SESSION_CLIENT = Platform.OS === 'web' ? 'web' : 'app';

export const authService = {
  async login(email: string, password: string) {
    const { data } = await api.post<{ user: User; token: string }>('/auth/login', { email, password, client: SESSION_CLIENT });
    return data;
  },
  async signup(data: { fullName: string; email: string; password?: string }) {
    const response = await api.post<{ user: User; token: string }>('/auth/signup', {
      full_name: data.fullName,
      email: data.email,
      password: data.password,
      client: SESSION_CLIENT,
    });
    return response.data;
  },
  async me() {
    return (await api.get<User>('/auth/me')).data;
  },
  async logout() {
    await api.post('/auth/logout');
  },
  /** Ends every session of this account, on every device. */
  async logoutEverywhere() {
    await api.post('/auth/logout-all');
  },
  /** Permanently deletes the account and everything it owns. */
  async deleteAccount(password: string) {
    await api.post('/auth/delete-account', { password });
  },
  async updateProfile(data: Partial<User>) {
    const { avatarUrl, ...rest } = data;
    const patch: Partial<User> = rest;
    if (avatarUrl && STORED_PHOTO.test(stripBase(avatarUrl))) {
      patch.avatarUrl = stripBase(avatarUrl);
    } else if (avatarUrl) {
      // A photo just picked on this device: upload it; the server stores a clean copy.
      await uploadProfilePhoto(avatarUrl);
    }
    return (await api.patch<User>('/users/me', patch)).data;
  },
};

type ApiCategory = ApiClothingItem['category'];

interface ApiImportPreview {
  preview_id: string;
  suggested_category: ApiCategory | null;
  person_found: boolean;
  original_url: string;
  candidates: Partial<Record<ApiCategory, { index: number; label: string; image_url: string }[]>>;
  source_title: string | null;
  suggested_size?: string | null;
}

export interface ImportCandidate { index: number; label: string; imageUrl: string }

/** A photo waiting for the user to confirm the garment and its category (ENGINEERING_PLAN 4.2b). */
export interface ImportPreview {
  id: string;
  suggestedCategory: ClothingCategory | null;
  /** Someone is wearing the garment, so cut-outs were made. */
  personFound: boolean;
  originalUrl: string;
  candidates: Partial<Record<ClothingCategory, ImportCandidate[]>>;
  sourceTitle: string | null;
  /** A size the shop page named (4.11), offered at confirm time. */
  suggestedSize: string | null;
}

function mapPreview(data: ApiImportPreview): ImportPreview {
  const candidates: Partial<Record<ClothingCategory, ImportCandidate[]>> = {};
  for (const [category, found] of Object.entries(data.candidates) as [ApiCategory, ApiImportPreview['candidates'][ApiCategory]][]) {
    if (found?.length) {
      candidates[categoryToApp[category]] = found.map((c) => ({ index: c.index, label: c.label, imageUrl: resolveApiUrl(c.image_url) }));
    }
  }
  return {
    id: data.preview_id,
    suggestedCategory: data.suggested_category ? categoryToApp[data.suggested_category] : null,
    personFound: data.person_found,
    originalUrl: resolveApiUrl(data.original_url),
    candidates,
    sourceTitle: data.source_title,
    suggestedSize: data.suggested_size ?? null,
  };
}

async function photoForm(userId: string, asset: UploadAsset): Promise<FormData> {
  const form = new FormData();
  form.append('user_id', userId);
  const name = asset.fileName || `wardrobe-${Date.now()}.jpg`;
  if (Platform.OS === 'web') {
    form.append('file', asset.file ?? await (await fetch(asset.uri)).blob(), name);
  } else {
    form.append('file', { uri: asset.uri, name, type: asset.mimeType || 'image/jpeg' } as unknown as Blob);
  }
  return form;
}

export const wardrobeService = {
  /** Upload a photo and get the garment cut-outs to choose from; nothing is saved yet. */
  async previewUpload(userId: string, asset: UploadAsset): Promise<ImportPreview> {
    return mapPreview((await api.post<ApiImportPreview>('/wardrobe/upload/preview', await photoForm(userId, asset))).data);
  },
  /** The same for a shopping link (product page or direct image address). */
  async previewLink(userId: string, url: string): Promise<ImportPreview> {
    return mapPreview((await api.post<ApiImportPreview>('/wardrobe/import-link/preview', { user_id: userId, url })).data);
  },
  /** Save the item: the chosen cut-out, or the original photo, in the user's category. */
  async confirmImport(previewId: string, choice: 'cutout' | 'original', category: ClothingCategory, index = 0, sizeLabel?: string): Promise<ClothingItem> {
    const { data } = await api.post<ApiClothingItem>(`/wardrobe/imports/${encodeURIComponent(previewId)}/confirm`, {
      choice, category: categoryToApi[category], index,
      ...(sizeLabel?.trim() ? { size: { label: sizeLabel.trim() } } : {}),
    });
    return mapItem(data);
  },
  async discardImport(previewId: string): Promise<void> {
    await api.delete(`/wardrobe/imports/${encodeURIComponent(previewId)}`);
  },
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
  /** Add an item from a shopping link (product page or direct image address). */
  async importFromLink(userId: string, url: string): Promise<ClothingItem> {
    const { data } = await api.post<ApiClothingItem>('/wardrobe/import-link', { user_id: userId, url });
    return mapItem(data);
  },
  /** Cut the garment out of a photo of someone wearing it, then re-identify it. */
  async removeModel(userId: string, id: string): Promise<ClothingItem> {
    const { data } = await api.post<ApiClothingItem>(
      `/wardrobe/${encodeURIComponent(userId)}/${encodeURIComponent(id)}/remove-model`,
    );
    return mapItem(data);
  },
  async updateItem(userId: string, id: string, data: Partial<ClothingItem>): Promise<ClothingItem> {
    const payload: Record<string, unknown> = {};
    if (data.category) payload.category = categoryToApi[data.category];
    if (data.name) payload.subcategory = data.name;
    if (data.color) payload.color_name = data.color;
    if (data.pattern) payload.pattern = data.pattern;
    // 'all' is saved as every season so it isn't mistaken for "unclassified" and re-inferred.
    if (data.season) payload.seasons = data.season === 'all'
      ? ['Spring', 'Summer', 'Autumn', 'Winter']
      : [data.season === 'fall' ? 'Autumn' : data.season.charAt(0).toUpperCase() + data.season.slice(1)];
    // An empty size object clears it on the server.
    if (data.size !== undefined) payload.size = data.size ?? {};
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
  /** Log pieces as worn today without a recommendation (e.g. from an item's own page). */
  async logWorn(userId: string, itemIds: string[]) {
    return (await api.post('/feedback', { user_id: userId, item_ids: itemIds, action: 'wear' })).data;
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

function mapProduct(product: Product): Product {
  return { ...product, imageUrls: product.imageUrls.map(resolveApiUrl) };
}

function mapOrder(order: MarketOrder): MarketOrder {
  return { ...order, imageUrl: resolveApiUrl(order.imageUrl) };
}

function mapConversation(conversation: Conversation): Conversation {
  return { ...conversation, product: { ...conversation.product, imageUrl: resolveApiUrl(conversation.product.imageUrl) } };
}

export interface NewListing {
  title: string;
  price: number;
  category: ClothingCategory;
  condition: ProductCondition;
  description: string;
  size: string;
  brand: string;
  /** Reuse this wardrobe item's photo as the first listing photo. */
  wardrobeItemId?: string;
  photos: UploadAsset[];
}

export const marketplaceService = {
  async getProducts(query = '', category = '') {
    const { data } = await api.get<Product[]>('/marketplace/products', { params: { q: query, category } });
    return data.map(mapProduct);
  },
  async getProduct(id: string) {
    return mapProduct((await api.get<Product>(`/marketplace/products/${encodeURIComponent(id)}`)).data);
  },
  async createListing(listing: NewListing) {
    const form = new FormData();
    form.append('title', listing.title);
    form.append('price', String(listing.price));
    form.append('category', listing.category);
    form.append('condition', listing.condition);
    form.append('description', listing.description);
    form.append('size', listing.size);
    form.append('brand', listing.brand);
    if (listing.wardrobeItemId) form.append('wardrobe_item_id', listing.wardrobeItemId);
    for (const [index, asset] of listing.photos.entries()) {
      const name = asset.fileName || `listing-${Date.now()}-${index}.jpg`;
      if (Platform.OS === 'web') {
        const blob = asset.file ?? await (await fetch(asset.uri)).blob();
        form.append('files', blob, name);
      } else {
        form.append('files', { uri: asset.uri, name, type: asset.mimeType || 'image/jpeg' } as unknown as Blob);
      }
    }
    return mapProduct((await api.post<Product>('/marketplace/listings', form)).data);
  },
  async updateListing(id: string, changes: Partial<Pick<Product, 'title' | 'price' | 'description' | 'size' | 'brand' | 'condition'>> & { status?: 'active' | 'paused' }) {
    return mapProduct((await api.patch<Product>(`/marketplace/listings/${encodeURIComponent(id)}`, changes)).data);
  },
  async deleteListing(id: string) {
    await api.delete(`/marketplace/listings/${encodeURIComponent(id)}`);
  },
  async getDashboard(): Promise<SellerDashboard> {
    const { data } = await api.get<SellerDashboard>('/marketplace/seller');
    return { ...data, listings: data.listings.map(mapProduct), orders: data.orders.map(mapOrder) };
  },
  async placeOrder(productIds: string[], shippingAddress: ShippingAddress, paymentMethod: PaymentMethod) {
    return (await api.post<{ order_ids: string[] }>('/marketplace/orders', {
      product_ids: productIds, shipping_address: shippingAddress, payment_method: paymentMethod,
    })).data.order_ids;
  },
  async getMyOrders() {
    return (await api.get<MarketOrder[]>('/marketplace/orders/mine')).data.map(mapOrder);
  },
  async updateOrderStatus(id: string, status: 'shipped' | 'completed' | 'cancelled') {
    return mapOrder((await api.post<MarketOrder>(`/marketplace/orders/${encodeURIComponent(id)}/status`, { status })).data);
  },
  async getConversations() {
    const { data } = await api.get<{ conversations: Conversation[]; unread: number }>('/marketplace/conversations');
    return { conversations: data.conversations.map(mapConversation), unread: data.unread };
  },
  /** Open the thread about a listing (buyer), or with a buyer who ordered it (seller). */
  async startConversation(productId: string, buyerId?: string) {
    return mapConversation((await api.post<Conversation>('/marketplace/conversations', {
      product_id: productId, buyer_id: buyerId,
    })).data);
  },
  async getConversation(id: string) {
    const { data } = await api.get<{ conversation: Conversation; messages: MarketMessage[] }>(
      `/marketplace/conversations/${encodeURIComponent(id)}`,
    );
    return { conversation: mapConversation(data.conversation), messages: data.messages };
  },
  async sendMessage(id: string, body: string) {
    return (await api.post<MarketMessage>(`/marketplace/conversations/${encodeURIComponent(id)}/messages`, { body })).data;
  },
};

function resolveChatImages(message: ChatMessage): ChatMessage {
  if (!message.outfit) return message;
  return {
    ...message,
    outfit: {
      ...message.outfit,
      imageUrl: resolveApiUrl(message.outfit.imageUrl),
      itemImages: message.outfit.itemImages?.map((piece) => ({ ...piece, url: resolveApiUrl(piece.url) })),
    },
  };
}

export const chatService = {
  async getMessages(sessionId: string) {
    const messages = (await api.get<ChatMessage[]>('/chat/messages', {
      params: { session_id: sessionId },
    })).data;
    return messages.map(resolveChatImages);
  },
  async sendMessage(content: string, sessionId: string) {
    const message = (await api.post<ChatMessage>('/chat/messages', {
      content,
      session_id: sessionId,
    })).data;
    return resolveChatImages(message);
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

export type ReportTarget = 'listing' | 'conversation' | 'post' | 'user';
export type ReportReason = 'spam' | 'scam' | 'offensive' | 'harassment' | 'prohibited_item' | 'other';
export interface BlockedUser { id: string; name: string; blockedAt: string }

/** Report and block (ENGINEERING_PLAN 4.4). */
export const moderationService = {
  async report(targetType: ReportTarget, targetId: string, reason: ReportReason, details = '') {
    await api.post('/reports', { target_type: targetType, target_id: targetId, reason, details });
  },
  async block(userId: string) {
    await api.post(`/users/${encodeURIComponent(userId)}/block`);
  },
  async unblock(userId: string) {
    await api.delete(`/users/${encodeURIComponent(userId)}/block`);
  },
  async blocked() {
    return (await api.get<BlockedUser[]>('/users/me/blocks')).data;
  },
};

export const donationService = {
  /** Items never marked as worn, owned for at least `minDays` days, oldest first. */
  async getCandidates(minDays = 0): Promise<DonationCandidate[]> {
    const { data } = await api.get<ApiClothingItem[]>('/donations/candidates', { params: { min_days: minDays } });
    return data.map((item) => ({ ...mapItem(item), daysInWardrobe: item.days_in_wardrobe ?? 0 }));
  },
  /** The same list as CSV text, ready to save or share. */
  async getCandidatesCsv(minDays = 0): Promise<string> {
    const { data } = await api.get<string>('/donations/candidates.csv', {
      params: { min_days: minDays },
      responseType: 'text',
      transformResponse: (body) => body,
    });
    return data;
  },
  async donate(itemIds: string[]): Promise<string[]> {
    return (await api.post<{ donated: string[] }>('/donations', { item_ids: itemIds })).data.donated;
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

// -- My Virtual Look: avatar + virtual try-on ----------------------------------------
interface ApiAvatar {
  avatar_id: string;
  view: AvatarView;
  image_url: string;
  analysis: Record<string, any>;
  created_at: string;
}

interface ApiRender {
  render_id: string;
  status: TryOnRender['status'];
  stage: string;
  progress: number;
  item_ids: string[];
  recommendation_id?: string | null;
  image_url?: string | null;
  not_rendered: string[];
  error?: string | null;
  saved: boolean;
  view?: AvatarView;
  disclaimer: string;
  created_at: string;
}

function mapAnalysis(raw: Record<string, any>): BodyAnalysis | undefined {
  if (!raw || !raw.body_shape) return undefined;
  return {
    bodyShape: raw.body_shape,
    bodyShapeReason: raw.body_shape_reason,
    confidence: raw.confidence,
    ratios: {
      shoulderToHip: raw.ratios?.shoulder_to_hip,
      waistToHip: raw.ratios?.waist_to_hip,
      waistToShoulder: raw.ratios?.waist_to_shoulder,
      torsoToLeg: raw.ratios?.torso_to_leg,
    },
    torsoLength: raw.torso_length,
    skinTone: raw.skin_tone
      ? { tone: raw.skin_tone.tone, sampleHex: raw.skin_tone.sample_hex, note: raw.skin_tone.note }
      : null,
    warnings: raw.warnings ?? [],
    method: raw.method,
  };
}

function mapAvatar(raw: ApiAvatar): VirtualAvatar {
  return {
    id: raw.avatar_id,
    view: raw.view,
    imageUrl: resolveApiUrl(raw.image_url),
    analysis: mapAnalysis(raw.analysis),
    createdAt: raw.created_at,
  };
}

function mapRender(raw: ApiRender): TryOnRender {
  return {
    id: raw.render_id,
    status: raw.status,
    stage: raw.stage,
    progress: raw.progress,
    itemIds: raw.item_ids,
    recommendationId: raw.recommendation_id,
    imageUrl: raw.image_url ? resolveApiUrl(raw.image_url) : undefined,
    notRendered: raw.not_rendered ?? [],
    error: raw.error,
    saved: raw.saved,
    view: raw.view,
    disclaimer: raw.disclaimer,
    createdAt: raw.created_at,
  };
}

interface ApiMeasurements {
  height_cm: number | null;
  measurements: BodyMeasurements['measurements'];
  labels: BodyMeasurements['labels'];
  estimate?: BodyMeasurements['lastEstimate'];
  method: string;
  status?: 'estimated' | 'not_estimated';
  problems?: string[];
}

function mapMeasurements(data: ApiMeasurements): BodyMeasurements {
  return { heightCm: data.height_cm, measurements: data.measurements, labels: data.labels, lastEstimate: data.estimate ?? null, method: data.method };
}

/** Body measurements in cm (4.11). Body data: only ever the signed-in user's own. */
export const measurementService = {
  async get(): Promise<BodyMeasurements> {
    return mapMeasurements((await api.get<ApiMeasurements>('/body/measurements')).data);
  },
  /** Typed values win over estimates; null clears a typed value. */
  async update(values: Partial<Record<MeasurementZone, number | null>> & { heightCm?: number }): Promise<BodyMeasurements> {
    const { heightCm, ...zones } = values;
    const payload = { ...zones, ...(heightCm ? { height_cm: heightCm } : {}) };
    return mapMeasurements((await api.put<ApiMeasurements>('/body/measurements', payload)).data);
  },
  /** Measure the front avatar and this side photo (the side photo is not stored). */
  async estimate(asset: UploadAsset, heightCm?: number): Promise<BodyMeasurements & { status: 'estimated' | 'not_estimated'; problems: string[] }> {
    const form = new FormData();
    const name = asset.fileName || `side-${Date.now()}.jpg`;
    if (Platform.OS === 'web') {
      form.append('file', asset.file ?? await (await fetch(asset.uri)).blob(), name);
    } else {
      form.append('file', { uri: asset.uri, name, type: asset.mimeType || 'image/jpeg' } as unknown as Blob);
    }
    if (heightCm) form.append('height_cm', String(heightCm));
    const { data } = await api.post<ApiMeasurements>('/body/measurements/estimate', form);
    return { ...mapMeasurements(data), status: data.status ?? 'not_estimated', problems: data.problems ?? [] };
  },
};

/** Size advice, computed for the signed-in user (4.11). Display only. */
export const fitService = {
  async forItem(userId: string, itemId: string): Promise<FitAdvice> {
    return (await api.get<FitAdvice>(`/wardrobe/${encodeURIComponent(userId)}/${encodeURIComponent(itemId)}/fit`)).data;
  },
  async forListing(productId: string): Promise<FitAdvice> {
    return (await api.get<FitAdvice>(`/marketplace/products/${encodeURIComponent(productId)}/fit`)).data;
  },
};

export const tryonService = {
  async getAvatars(): Promise<{ avatars: Partial<Record<AvatarView, VirtualAvatar>>; status: TryOnStatus; consentGiven: boolean }> {
    const { data } = await api.get<{ avatars: Record<string, ApiAvatar>; status: Record<string, any>; consent_given?: boolean }>('/avatar');
    const avatars: Partial<Record<AvatarView, VirtualAvatar>> = {};
    Object.values(data.avatars).forEach((avatar) => { avatars[avatar.view] = mapAvatar(avatar); });
    return {
      avatars,
      consentGiven: Boolean(data.consent_given),
      status: {
        enabled: data.status.enabled,
        bodyAnalysisReady: data.status.body_analysis_ready,
        tryonReady: data.status.tryon_ready,
        missingFiles: data.status.missing_files ?? [],
        disclaimer: data.status.disclaimer,
        queueLength: data.status.queue_length ?? 0,
      },
    };
  },
  /** `consent` is the user's answer on the consent screen; the server records it once. */
  async uploadAvatar(asset: UploadAsset, view: AvatarView, consent = false): Promise<VirtualAvatar> {
    const form = new FormData();
    form.append('view', view);
    if (consent) form.append('consent', 'true');
    const name = asset.fileName || `body-${Date.now()}.jpg`;
    if (Platform.OS === 'web') {
      const blob = asset.file ?? await (await fetch(asset.uri)).blob();
      form.append('file', blob, name);
    } else {
      form.append('file', { uri: asset.uri, name, type: asset.mimeType || 'image/jpeg' } as unknown as Blob);
    }
    return mapAvatar((await api.post<ApiAvatar>('/avatar', form)).data);
  },
  async deleteAvatars() {
    await api.delete('/avatar');
  },
  async startRender(itemIds: string[], view: AvatarView, recommendationId?: string): Promise<TryOnRender> {
    const { data } = await api.post<ApiRender>('/tryon', {
      item_ids: itemIds,
      view,
      recommendation_id: recommendationId,
    });
    return mapRender(data);
  },
  async getRender(id: string): Promise<TryOnRender> {
    return mapRender((await api.get<ApiRender>(`/tryon/${encodeURIComponent(id)}`)).data);
  },
  async saveRender(id: string, saved = true): Promise<TryOnRender> {
    return mapRender((await api.post<ApiRender>(`/tryon/${encodeURIComponent(id)}/save`, null, { params: { saved } })).data);
  },
  async savedLooks(): Promise<TryOnRender[]> {
    return (await api.get<ApiRender[]>('/tryon/saved')).data.map(mapRender);
  },
};
