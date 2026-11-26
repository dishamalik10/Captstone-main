import { create } from 'zustand';
import type { Product } from '@/types';

interface CartItem {
  product: Product;
  quantity: number;
}

interface CartState {
  items: CartItem[];
  addToCart: (product: Product) => void;
  removeFromCart: (productId: string) => void;
  updateQty: (productId: string, quantity: number) => void;
  clearCart: () => void;
  total: () => number;
  itemCount: () => number;
}

export const useCartStore = create<CartState>((set, get) => ({
  items: [],

  // Marketplace pieces are one-offs: an item is either in the bag or not.
  addToCart: (product) =>
    set((s) => (s.items.some((i) => i.product.id === product.id)
      ? s
      : { items: [...s.items, { product, quantity: 1 }] })),

  removeFromCart: (productId) =>
    set((s) => ({ items: s.items.filter((i) => i.product.id !== productId) })),

  updateQty: (productId, quantity) =>
    set((s) => ({
      items:
        quantity <= 0
          ? s.items.filter((i) => i.product.id !== productId)
          : s.items.map((i) => (i.product.id === productId ? { ...i, quantity } : i)),
    })),

  clearCart: () => set({ items: [] }),

  total: () => get().items.reduce((sum, i) => sum + i.product.price * i.quantity, 0),

  itemCount: () => get().items.reduce((sum, i) => sum + i.quantity, 0),
}));
