import type {
  ChatMessage,
  ClothingItem,
  Outfit,
  Product,
  SellerListing,
  SellerOrder,
  SellerStats,
  SocialPost,
  User,
  WardrobeStats,
  WearLog,
  Weather,
} from '@/types';

const img = (id: number, w = 400, h = 500) =>
  `https://images.unsplash.com/photo-${1500000000000 + id}?w=${w}&h=${h}&fit=crop`;

export const mockUser: User = {
  id: 'user-1',
  fullName: 'Akarsh',
  email: 'akarsh@wearbefore.com',
  avatarUrl: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=200&h=200&fit=crop',
  location: 'New Delhi',
  stylePreferences: ['minimalist', 'smart_casual'],
  bodyShape: 'athletic',
  skinTone: 'medium',
  heightCm: 178,
  topSize: 'M',
  bottomSize: 'M',
  itemsCount: 20,
  outfitsSaved: 8,
  following: 124,
  followers: 89,
  profileComplete: true,
};

export const mockWeather: Weather = {
  temperature: 34,
  condition: 'Sunny',
  icon: 'sunny',
  location: 'New Delhi',
};

export const mockClothingItems: ClothingItem[] = [
  { id: 'c1', name: 'Linen Shirt', category: 'tops', color: 'White', colorHex: '#F5F5F0', pattern: 'Solid', brand: 'Zara', season: 'summer', imageUrl: 'https://images.unsplash.com/photo-1596755094514-f87e34085b2c?w=400&h=500&fit=crop', wearCount: 12, lastWorn: '2026-06-28', createdAt: '2025-01-15' },
  { id: 'c2', name: 'Navy Blazer', category: 'tops', color: 'Navy', colorHex: '#1B2A4A', pattern: 'Solid', brand: 'H&M', season: 'all', imageUrl: 'https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=400&h=500&fit=crop', wearCount: 8, lastWorn: '2026-06-25', createdAt: '2025-02-10' },
  { id: 'c3', name: 'Black Tee', category: 'tops', color: 'Black', colorHex: '#0A0A0A', pattern: 'Solid', brand: 'Uniqlo', season: 'all', imageUrl: 'https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=400&h=500&fit=crop', wearCount: 24, lastWorn: '2026-06-29', createdAt: '2024-11-20' },
  { id: 'c4', name: 'Silk Blouse', category: 'tops', color: 'Beige', colorHex: '#D4C4A8', pattern: 'Solid', brand: 'Mango', season: 'spring', imageUrl: 'https://images.unsplash.com/photo-1564257631407-4deb1f99d992?w=400&h=500&fit=crop', wearCount: 5, createdAt: '2025-03-05' },
  { id: 'c5', name: 'Striped Polo', category: 'tops', color: 'Blue', colorHex: '#4A6FA5', pattern: 'Striped', brand: 'Ralph Lauren', season: 'summer', imageUrl: 'https://images.unsplash.com/photo-1586363104862-3a5e2ab60d99?w=400&h=500&fit=crop', wearCount: 6, createdAt: '2025-04-12' },
  { id: 'c6', name: 'Slim Chinos', category: 'bottoms', color: 'Khaki', colorHex: '#C3B091', pattern: 'Solid', brand: 'Zara', season: 'all', imageUrl: 'https://images.unsplash.com/photo-1473966968600-fa801b869a1a?w=400&h=500&fit=crop', wearCount: 15, lastWorn: '2026-06-27', createdAt: '2025-01-20' },
  { id: 'c7', name: 'Dark Denim', category: 'bottoms', color: 'Indigo', colorHex: '#1A237E', pattern: 'Solid', brand: "Levi's", season: 'all', imageUrl: 'https://images.unsplash.com/photo-1542272604-787c3835535d?w=400&h=500&fit=crop', wearCount: 18, lastWorn: '2026-06-29', createdAt: '2024-10-05' },
  { id: 'c8', name: 'Tailored Trousers', category: 'bottoms', color: 'Grey', colorHex: '#6B6B6B', pattern: 'Solid', brand: 'H&M', season: 'fall', imageUrl: 'https://images.unsplash.com/photo-1624378515195-6bbdb73f2194?w=400&h=500&fit=crop', wearCount: 9, createdAt: '2025-02-28' },
  { id: 'c9', name: 'Midi Dress', category: 'dresses', color: 'Emerald', colorHex: '#2E7D32', pattern: 'Solid', brand: 'Reformation', season: 'spring', imageUrl: 'https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=400&h=500&fit=crop', wearCount: 4, createdAt: '2025-05-01' },
  { id: 'c10', name: 'Floral Maxi', category: 'dresses', color: 'Multi', colorHex: '#E8B4B8', pattern: 'Floral', brand: 'Free People', season: 'summer', imageUrl: 'https://images.unsplash.com/photo-1612336307429-8a898d40e087?w=400&h=500&fit=crop', wearCount: 3, createdAt: '2025-05-15' },
  { id: 'c11', name: 'White Sneakers', category: 'shoes', color: 'White', colorHex: '#F5F5F0', pattern: 'Solid', brand: 'Nike', season: 'all', imageUrl: 'https://images.unsplash.com/photo-1549298916-b41d501d3772?w=400&h=500&fit=crop', wearCount: 30, lastWorn: '2026-06-29', createdAt: '2024-09-10' },
  { id: 'c12', name: 'Leather Loafers', category: 'shoes', color: 'Brown', colorHex: '#5D4037', pattern: 'Solid', brand: 'Clarks', season: 'fall', imageUrl: 'https://images.unsplash.com/photo-1533867612531-9ebbfc01eecf?w=400&h=500&fit=crop', wearCount: 7, createdAt: '2025-01-08' },
  { id: 'c13', name: 'Ankle Boots', category: 'shoes', color: 'Black', colorHex: '#0A0A0A', pattern: 'Solid', brand: 'Dr. Martens', season: 'winter', imageUrl: 'https://images.unsplash.com/photo-1608256246200-53bd35f4f617?w=400&h=500&fit=crop', wearCount: 5, createdAt: '2024-12-01' },
  { id: 'c14', name: 'Gold Watch', category: 'accessories', color: 'Gold', colorHex: '#C8A96E', pattern: 'Solid', brand: 'Fossil', season: 'all', imageUrl: 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=400&h=500&fit=crop', wearCount: 22, createdAt: '2024-08-15' },
  { id: 'c15', name: 'Leather Belt', category: 'accessories', color: 'Brown', colorHex: '#5D4037', pattern: 'Solid', brand: 'H&M', season: 'all', imageUrl: 'https://images.unsplash.com/photo-1624222247344-550fb60583fd?w=400&h=500&fit=crop', wearCount: 14, createdAt: '2024-10-20' },
  { id: 'c16', name: 'Silk Scarf', category: 'accessories', color: 'Red', colorHex: '#C62828', pattern: 'Printed', brand: 'Hermès', season: 'fall', imageUrl: 'https://images.unsplash.com/photo-1601924994987-69e26d50dc26?w=400&h=500&fit=crop', wearCount: 2, createdAt: '2025-06-01' },
  { id: 'c17', name: 'Cashmere Sweater', category: 'tops', color: 'Camel', colorHex: '#C19A6B', pattern: 'Solid', brand: 'COS', season: 'winter', imageUrl: 'https://images.unsplash.com/photo-1576566588028-4147f3842f27?w=400&h=500&fit=crop', wearCount: 6, createdAt: '2024-11-01' },
  { id: 'c18', name: 'Cargo Pants', category: 'bottoms', color: 'Olive', colorHex: '#556B2F', pattern: 'Solid', brand: 'Carhartt', season: 'fall', imageUrl: 'https://images.unsplash.com/photo-1591195853828-11db59a44f6b?w=400&h=500&fit=crop', wearCount: 4, createdAt: '2025-03-20' },
  { id: 'c19', name: 'Running Shoes', category: 'shoes', color: 'Grey', colorHex: '#9E9E9E', pattern: 'Solid', brand: 'Adidas', season: 'all', imageUrl: 'https://images.unsplash.com/photo-1606107557195-0e29a4b5b4aa?w=400&h=500&fit=crop', wearCount: 11, createdAt: '2025-02-15' },
  { id: 'c20', name: 'Aviator Sunglasses', category: 'accessories', color: 'Gold', colorHex: '#C8A96E', pattern: 'Solid', brand: 'Ray-Ban', season: 'summer', imageUrl: 'https://images.unsplash.com/photo-1572635196233-1594d08d8b0c?w=400&h=500&fit=crop', wearCount: 8, createdAt: '2025-04-01' },
];

export const mockOutfits: Outfit[] = [
  { id: 'o1', name: 'Summer Brunch', occasion: 'casual', compatibilityScore: 94, imageUrl: 'https://images.unsplash.com/photo-1496747611176-843222e1e57c?w=600&h=800&fit=crop', itemIds: ['c1', 'c6', 'c11', 'c20'], explanation: 'Light linen and neutral tones balance the Delhi heat perfectly.' },
  { id: 'o2', name: 'Boardroom Ready', occasion: 'meeting', compatibilityScore: 91, imageUrl: 'https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=600&h=800&fit=crop', itemIds: ['c2', 'c8', 'c12', 'c14'], explanation: 'Structured blazer with tailored trousers creates a polished silhouette.' },
  { id: 'o3', name: 'Date Night', occasion: 'date', compatibilityScore: 88, imageUrl: 'https://images.unsplash.com/photo-1515372039744-b8f02a3ae446?w=600&h=800&fit=crop', itemIds: ['c3', 'c7', 'c11', 'c15'], explanation: 'Dark denim with a fitted tee — effortlessly refined.' },
  { id: 'o4', name: 'Garden Party', occasion: 'party', compatibilityScore: 86, imageUrl: 'https://images.unsplash.com/photo-1469334031218-e382a71b716b?w=600&h=800&fit=crop', itemIds: ['c4', 'c9', 'c11', 'c16'], explanation: 'Soft textures and emerald tones complement outdoor settings.' },
  { id: 'o5', name: 'Interview Sharp', occasion: 'interview', compatibilityScore: 92, imageUrl: 'https://images.unsplash.com/photo-1560250097-0b93528c311a?w=600&h=800&fit=crop', itemIds: ['c2', 'c6', 'c12', 'c14'], explanation: 'Classic navy and khaki convey confidence without distraction.' },
  { id: 'o6', name: 'Wedding Guest', occasion: 'wedding', compatibilityScore: 89, imageUrl: 'https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=600&h=800&fit=crop', itemIds: ['c4', 'c8', 'c12', 'c16'], explanation: 'Elegant layers with a statement scarf for festive flair.' },
  { id: 'o7', name: 'Travel Comfort', occasion: 'travel', compatibilityScore: 87, imageUrl: 'https://images.unsplash.com/photo-1487222477894-8943e31a7e66?w=600&h=800&fit=crop', itemIds: ['c3', 'c6', 'c19', 'c20'], explanation: 'Breathable layers and sneakers for long journeys.' },
  { id: 'o8', name: 'Winter Layers', occasion: 'casual', compatibilityScore: 85, imageUrl: 'https://images.unsplash.com/photo-1434389677669-e08b4cac3105?w=600&h=800&fit=crop', itemIds: ['c17', 'c7', 'c13', 'c15'], explanation: 'Warm cashmere paired with rugged boots for cold evenings.' },
];

const mockSeller = {
  id: 'seller-1',
  name: 'Priya Sharma',
  avatarUrl: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=100&h=100&fit=crop',
  rating: 4.8,
  responseTime: '< 1 hour',
};

export const mockProducts: Product[] = [
  { id: 'p1', title: 'Vintage Denim Jacket', price: 2499, imageUrls: ['https://images.unsplash.com/photo-1551028719-00167b16eac5?w=400&h=500&fit=crop'], category: 'tops', condition: 'good', seller: mockSeller, description: 'Classic 90s denim jacket in excellent vintage condition.', isNew: true, rating: 4.7, reviewCount: 23 },
  { id: 'p2', title: 'Silk Saree Blouse', price: 1899, imageUrls: ['https://images.unsplash.com/photo-1610030469983-98e550d6193c?w=400&h=500&fit=crop'], category: 'tops', condition: 'like_new', seller: mockSeller, description: 'Handcrafted silk blouse with intricate embroidery.', rating: 4.9, reviewCount: 15 },
  { id: 'p3', title: 'Palazzo Pants', price: 1299, imageUrls: ['https://images.unsplash.com/photo-1594633312681-425c7b97ccd1?w=400&h=500&fit=crop'], category: 'bottoms', condition: 'new', seller: mockSeller, description: 'Flowy palazzo pants perfect for summer.', isNew: true, rating: 4.5, reviewCount: 8 },
  { id: 'p4', title: 'Leather Ankle Boots', price: 4599, imageUrls: ['https://images.unsplash.com/photo-1608256246200-53bd35f4f617?w=400&h=500&fit=crop'], category: 'shoes', condition: 'like_new', seller: mockSeller, description: 'Barely worn leather boots, size 8.', rating: 4.6, reviewCount: 12 },
  { id: 'p5', title: 'Statement Earrings', price: 599, imageUrls: ['https://images.unsplash.com/photo-1535632066927-ab7c9ab60908?w=400&h=500&fit=crop'], category: 'accessories', condition: 'new', seller: mockSeller, description: 'Gold-plated statement earrings.', rating: 4.8, reviewCount: 31 },
  { id: 'p6', title: 'Linen Kurta', price: 1699, imageUrls: ['https://images.unsplash.com/photo-1598033129183-c4f50c736f10?w=400&h=500&fit=crop'], category: 'tops', condition: 'good', seller: mockSeller, description: 'Breathable linen kurta for everyday wear.', rating: 4.4, reviewCount: 19 },
  { id: 'p7', title: 'High-Waist Jeans', price: 2199, imageUrls: ['https://images.unsplash.com/photo-1541099649105-f69ad21f3246?w=400&h=500&fit=crop'], category: 'bottoms', condition: 'like_new', seller: mockSeller, description: 'Trendy high-waist fit, dark wash.', isNew: true, rating: 4.7, reviewCount: 27 },
  { id: 'p8', title: 'Canvas Sneakers', price: 1499, imageUrls: ['https://images.unsplash.com/photo-1525966220534-9dec02de445a?w=400&h=500&fit=crop'], category: 'shoes', condition: 'good', seller: mockSeller, description: 'Comfortable everyday sneakers.', rating: 4.3, reviewCount: 44 },
  { id: 'p9', title: 'Crossbody Bag', price: 3299, imageUrls: ['https://images.unsplash.com/photo-1548036328-c9fa89d128fa?w=400&h=500&fit=crop'], category: 'accessories', condition: 'like_new', seller: mockSeller, description: 'Minimalist leather crossbody bag.', rating: 4.9, reviewCount: 18 },
  { id: 'p10', title: 'Floral Wrap Dress', price: 2799, imageUrls: ['https://images.unsplash.com/photo-1572804013309-59a23b99e04f?w=400&h=500&fit=crop'], category: 'dresses', condition: 'new', seller: mockSeller, description: 'Elegant wrap dress for special occasions.', isNew: true, rating: 4.8, reviewCount: 9 },
];

export const mockChatMessages: ChatMessage[] = [
  { id: 'm1', role: 'user', content: 'What should I wear today?', timestamp: '2026-06-29T08:00:00Z' },
  { id: 'm2', role: 'assistant', content: "Given the 34°C sunny weather in New Delhi, I'd recommend your Summer Brunch look — light linen keeps you cool while looking polished.", timestamp: '2026-06-29T08:00:05Z', outfit: mockOutfits[0] },
  { id: 'm3', role: 'user', content: 'What matches this navy blazer?', timestamp: '2026-06-29T08:05:00Z' },
  { id: 'm4', role: 'assistant', content: 'Your tailored trousers and leather loafers pair beautifully with the navy blazer. Here are trending colors this season:', timestamp: '2026-06-29T08:05:08Z', colorPalette: ['#1B2A4A', '#C3B091', '#5D4037', '#F5F5F0', '#C8A96E'] },
  { id: 'm5', role: 'assistant', content: 'Also check out this vintage denim jacket from our marketplace — it would add a casual edge to your blazer.', timestamp: '2026-06-29T08:05:12Z', product: mockProducts[0] },
];

export const mockSocialPosts: SocialPost[] = [
  { id: 's1', user: { id: 'u2', fullName: 'Ananya Kapoor', avatarUrl: 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=100&h=100&fit=crop' }, outfitImageUrl: 'https://images.unsplash.com/photo-1515372039744-b8f02a3ae446?w=600&h=800&fit=crop', caption: 'Sunday brunch vibes ☀️', likes: 234, comments: 18, liked: false, shopProductIds: ['p3', 'p5'], createdAt: '2026-06-28T10:00:00Z' },
  { id: 's2', user: { id: 'u3', fullName: 'Rohan Mehta', avatarUrl: 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=100&h=100&fit=crop' }, outfitImageUrl: 'https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=600&h=800&fit=crop', caption: 'Boardroom to bar — one outfit.', likes: 189, comments: 12, liked: true, shopProductIds: ['p1'], createdAt: '2026-06-27T14:30:00Z' },
  { id: 's3', user: { id: 'u4', fullName: 'Meera Singh', avatarUrl: 'https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=100&h=100&fit=crop' }, outfitImageUrl: 'https://images.unsplash.com/photo-1469334031218-e382a71b716b?w=600&h=800&fit=crop', caption: 'Garden party ready 🌸', likes: 412, comments: 34, liked: false, shopProductIds: ['p10'], createdAt: '2026-06-26T09:15:00Z' },
];

export const mockWardrobeStats: WardrobeStats = {
  totalItems: 20,
  mostWorn: { name: 'White Sneakers', count: 30 },
  leastWorn: { name: 'Silk Scarf', count: 2 },
};

export const mockSellerStats: SellerStats = {
  totalSales: 47,
  revenue: 89450,
  activeListings: 6,
};

export const mockSellerListings: SellerListing[] = [
  { id: 'sl1', title: 'Vintage Denim Jacket', price: 2499, imageUrl: mockProducts[0].imageUrls[0], status: 'active' },
  { id: 'sl2', title: 'Silk Saree Blouse', price: 1899, imageUrl: mockProducts[1].imageUrls[0], status: 'active' },
  { id: 'sl3', title: 'Palazzo Pants', price: 1299, imageUrl: mockProducts[2].imageUrls[0], status: 'paused' },
];

export const mockSellerOrders: SellerOrder[] = [
  { id: 'so1', productTitle: 'Statement Earrings', status: 'pending', amount: 599, date: '2026-06-29' },
  { id: 'so2', productTitle: 'Canvas Sneakers', status: 'shipped', amount: 1499, date: '2026-06-27' },
  { id: 'so3', productTitle: 'Linen Kurta', status: 'completed', amount: 1699, date: '2026-06-25' },
];

export const mockWearLogs: WearLog[] = [
  { id: 'w1', outfitName: 'Summer Brunch', date: '2026-06-29' },
  { id: 'w2', outfitName: 'Boardroom Ready', date: '2026-06-25' },
  { id: 'w3', outfitName: 'Date Night', date: '2026-06-22' },
];

export const mockUsers: User[] = [
  mockUser,
  { ...mockUser, id: 'u2', fullName: 'Ananya Kapoor', avatarUrl: 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=200&h=200&fit=crop', followers: 1200, following: 340, itemsCount: 45 },
  { ...mockUser, id: 'u3', fullName: 'Rohan Mehta', avatarUrl: 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=200&h=200&fit=crop', followers: 890, following: 210, itemsCount: 32 },
];
