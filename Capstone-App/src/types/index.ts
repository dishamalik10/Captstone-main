export type ClothingCategory =
  | 'tops'
  | 'bottoms'
  | 'dresses'
  | 'shoes'
  | 'outerwear'
  | 'accessories';

export type Season = 'spring' | 'summer' | 'fall' | 'winter' | 'all';

export type Occasion =
  | 'date'
  | 'party'
  | 'meeting'
  | 'casual'
  | 'wedding'
  | 'interview'
  | 'travel';

export type StylePreference =
  | 'minimalist'
  | 'streetwear'
  | 'formal'
  | 'bohemian'
  | 'athleisure'
  | 'vintage'
  | 'smart_casual'
  | 'edgy';

export type BodyShape =
  | 'hourglass'
  | 'rectangle'
  | 'pear'
  | 'apple'
  | 'athletic';

export type SkinTone = 'fair' | 'light' | 'medium' | 'olive' | 'tan' | 'deep';

export type Size = 'XS' | 'S' | 'M' | 'L' | 'XL' | 'XXL';

export interface ClothingItem {
  id: string;
  name: string;
  category: ClothingCategory;
  color: string;
  colorHex: string;
  pattern: string;
  brand: string;
  season: Season;
  imageUrl: string;
  wearCount: number;
  lastWorn?: string;
  createdAt: string;
  confidence?: number;
  needsReview?: boolean;
  subcategory?: string;
  garmentGroup?: string;
  /** Shop link the item was imported from, if any. */
  sourceUrl?: string;
  sourceTitle?: string;
  /** True when AURA removed a model/background so only the garment remains. */
  garmentCutout?: boolean;
  /** The garment's size, if the user added one (4.11). null = unknown. */
  size?: GarmentSize | null;
}

/** Flat garment measurements in cm (laid flat, edge to edge). */
export interface GarmentMeasurements {
  chest_flat_cm?: number | null;
  waist_flat_cm?: number | null;
  hip_flat_cm?: number | null;
  /** Tops and dresses: high point of the shoulder to the hem. */
  length_cm?: number | null;
  inseam_cm?: number | null;
}

export interface GarmentSize {
  label?: string | null;
  chart?: 'women' | 'men' | 'unisex' | null;
  measurements?: GarmentMeasurements | null;
}

export type FitRating = 'tight' | 'snug' | 'regular' | 'relaxed' | 'loose';

/** Size advice for one garment, for the signed-in user only (4.11). */
export interface FitAdvice {
  available: boolean;
  reason?: string;
  verdict?: string;
  estimated?: boolean;
  zones?: { zone: string; rating: FitRating; body_cm: number; garment_cm: number; ease_cm: number }[];
  lengths?: { zone: string; rating: string; difference_cm: number }[];
  garment_basis?: string;
  notes?: string[];
}

export type MeasurementZone = 'chest' | 'waist' | 'hip' | 'shoulder' | 'inseam' | 'arm' | 'torso';

export interface Measurement {
  value: number;
  source: 'you' | 'estimated';
  low?: number;
  high?: number;
  /** Not yet shown to be within +-4 cm: show the range, not the number. */
  range_only?: boolean;
}

export interface BodyMeasurements {
  heightCm: number | null;
  measurements: Partial<Record<MeasurementZone, Measurement>>;
  labels: Record<MeasurementZone, string>;
  lastEstimate?: { at: string; status: 'estimated' | 'not_estimated'; problems: string[] } | null;
  method: string;
}

/** A wardrobe item that has never been marked as worn. */
export interface DonationCandidate extends ClothingItem {
  daysInWardrobe: number;
}

export interface Outfit {
  id: string;
  name: string;
  occasion: Occasion;
  compatibilityScore: number;
  imageUrl: string;
  /** Every piece's photo, so the outfit can be shown as one combined look. */
  itemImages?: { url: string; label: string; id?: string }[];
  itemIds: string[];
  explanation: string;
  saved?: boolean;
  componentScores?: Record<string, number>;
  comparisonExplanation?: string;
  comparisonAlternative?: string;
  comparisonSource?: 'local_llm' | 'rules';
  evidenceConfidence?: 'limited' | 'moderate';
  confidenceNote?: string;
  scoreDisclosure?: string;
}

export interface User {
  id: string;
  fullName: string;
  email: string;
  avatarUrl?: string;
  location: string;
  stylePreferences: StylePreference[];
  bodyShape?: BodyShape;
  skinTone?: SkinTone;
  heightCm?: number;
  topSize?: Size;
  bottomSize?: Size;
  itemsCount: number;
  outfitsSaved: number;
  following: number;
  followers: number;
  profileComplete: boolean;
}

export type ProductCondition = 'new' | 'like_new' | 'good' | 'fair';

export interface Seller {
  id: string;
  name: string;
  avatarUrl: string;
  /** Orders this seller has shipped or completed. */
  sales: number;
  memberSince: string;
}

export type ListingStatus = 'active' | 'paused' | 'sold';

export interface Product {
  id: string;
  title: string;
  price: number;
  imageUrls: string[];
  category: ClothingCategory;
  condition: ProductCondition;
  seller: Seller;
  description: string;
  size: string;
  brand: string;
  status: ListingStatus;
  createdAt: string;
  wardrobeItemId?: string | null;
  isNew?: boolean;
}

export interface CartItem {
  product: Product;
  quantity: number;
}

export type MessageRole = 'user' | 'assistant';

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: string;
  outfit?: Outfit;
  product?: Product;
  colorPalette?: string[];
}

export interface SocialPost {
  id: string;
  user: Pick<User, 'id' | 'fullName' | 'avatarUrl'>;
  outfitImageUrl: string;
  caption: string;
  likes: number;
  comments: number;
  liked: boolean;
  shopProductIds: string[];
  createdAt: string;
}

export interface Weather {
  temperature: number;
  condition: string;
  icon: string;
  location: string;
  /** Which season's clothes suit this temperature (from the backend). */
  season?: 'Summer' | 'Winter' | 'Mild';
}

export interface WardrobeStats {
  totalItems: number;
  mostWorn: { name: string; count: number };
  leastWorn: { name: string; count: number };
}

export interface StylePurchaseRecommendation {
  category: string;
  title: string;
  reason: string;
  priority: 'high' | 'medium' | 'low';
  owned: number;
  suggestedMinimum: number;
}

export interface StyleAnalysis {
  totalItems: number;
  wardrobeCoverage: number;
  categoryCounts: Record<string, number>;
  dominantColors: Array<{ name: string; count: number }>;
  dominantStyles: string[];
  strengths: string[];
  recommendations: StylePurchaseRecommendation[];
  disclaimer: string;
}

export interface PurchaseImpact {
  detectedItem: {
    category: string;
    productType: string;
    color: string;
    confidence: number;
  };
  purchaseScore: number;
  verdict: string;
  headline: string;
  newOutfits: number;
  similarItems: Array<{
    id: string;
    name: string;
    color: string;
    imageUrl: string;
  }>;
  reasons: string[];
  disclaimer: string;
}

export type OrderStatus = 'pending' | 'shipped' | 'completed' | 'cancelled';
export type PaymentMethod = 'cod' | 'upi';

export interface ShippingAddress {
  name: string;
  phone: string;
  line1: string;
  city: string;
  pincode: string;
}

export interface MarketOrder {
  id: string;
  productId: string;
  productTitle: string;
  imageUrl: string;
  amount: number;
  status: OrderStatus;
  date: string;
  updatedAt: string;
  buyer: { id: string; name: string };
  seller: { id: string; name: string };
  shippingAddress: Partial<ShippingAddress>;
  paymentMethod: PaymentMethod;
}

export interface SellerStats {
  totalSales: number;
  revenue: number;
  activeListings: number;
  pendingOrders: number;
  unreadMessages: number;
}

export interface SellerDashboard {
  stats: SellerStats;
  listings: Product[];
  orders: MarketOrder[];
}

export interface Conversation {
  id: string;
  role: 'buyer' | 'seller';
  product: { id: string; title: string; price: number; imageUrl: string; status: ListingStatus };
  otherUser: { id: string; name: string; avatarUrl: string; online?: boolean };
  lastMessage: string;
  lastMessageAt: string;
  lastMessageMine: boolean;
  unread: number;
}

export interface MarketMessage {
  id: string;
  body: string;
  createdAt: string;
  mine: boolean;
  read: boolean;
}

export interface WearLog {
  id: string;
  outfitName: string;
  date: string;
}

// -- My Virtual Look ------------------------------------------------------------------
export type AvatarView = 'front' | 'side';

export interface BodyAnalysis {
  bodyShape: BodyShape;
  bodyShapeReason: string;
  confidence: 'low' | 'medium';
  ratios: { shoulderToHip: number; waistToHip: number; waistToShoulder: number; torsoToLeg: number };
  torsoLength: 'short' | 'balanced' | 'long';
  skinTone?: { tone: SkinTone; sampleHex: string; note: string } | null;
  warnings: string[];
  method: string;
}

export interface VirtualAvatar {
  id: string;
  view: AvatarView;
  imageUrl: string;
  analysis?: BodyAnalysis;
  createdAt: string;
}

export interface TryOnStatus {
  enabled: boolean;
  bodyAnalysisReady: boolean;
  tryonReady: boolean;
  missingFiles: string[];
  disclaimer: string;
  queueLength: number;
}

export type TryOnState = 'queued' | 'running' | 'done' | 'failed';

export interface TryOnRender {
  id: string;
  status: TryOnState;
  stage: string;
  progress: number;
  itemIds: string[];
  recommendationId?: string | null;
  imageUrl?: string;
  notRendered: string[];
  error?: string | null;
  saved: boolean;
  view?: AvatarView;
  disclaimer: string;
  createdAt: string;
}
