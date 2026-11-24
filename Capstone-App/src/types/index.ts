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
}

export interface Outfit {
  id: string;
  name: string;
  occasion: Occasion;
  compatibilityScore: number;
  imageUrl: string;
  /** Every piece's photo, so the outfit can be shown as one combined look. */
  itemImages?: { url: string; label: string }[];
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
  rating: number;
  responseTime: string;
}

export interface Product {
  id: string;
  title: string;
  price: number;
  imageUrls: string[];
  category: ClothingCategory;
  condition: ProductCondition;
  seller: Seller;
  description: string;
  isNew?: boolean;
  rating: number;
  reviewCount: number;
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

export interface SellerStats {
  totalSales: number;
  revenue: number;
  activeListings: number;
}

export interface SellerOrder {
  id: string;
  productTitle: string;
  status: 'pending' | 'shipped' | 'completed';
  amount: number;
  date: string;
}

export interface SellerListing {
  id: string;
  title: string;
  price: number;
  imageUrl: string;
  status: 'active' | 'paused';
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
