import { create } from 'zustand';
import type { ClothingCategory, ClothingItem } from '@/types';

interface WardrobeFilters {
  category?: ClothingCategory | 'all';
  color?: string;
  season?: string;
  brand?: string;
  search?: string;
}

interface WardrobeState {
  items: ClothingItem[];
  filters: WardrobeFilters;
  setItems: (items: ClothingItem[]) => void;
  addItem: (item: ClothingItem) => void;
  removeItem: (id: string) => void;
  updateItem: (id: string, data: Partial<ClothingItem>) => void;
  setFilters: (filters: Partial<WardrobeFilters>) => void;
  filterItems: () => ClothingItem[];
  incrementWearCount: (id: string) => void;
}

export const useWardrobeStore = create<WardrobeState>((set, get) => ({
  items: [],
  filters: { category: 'all' },

  setItems: (items) => set({ items }),

  addItem: (item) => set((s) => ({ items: [item, ...s.items] })),

  removeItem: (id) => set((s) => ({ items: s.items.filter((i) => i.id !== id) })),

  updateItem: (id, data) =>
    set((s) => ({
      items: s.items.map((i) => (i.id === id ? { ...i, ...data } : i)),
    })),

  setFilters: (filters) => set((s) => ({ filters: { ...s.filters, ...filters } })),

  filterItems: () => {
    const { items, filters } = get();
    return items.filter((item) => {
      if (filters.category && filters.category !== 'all' && item.category !== filters.category) return false;
      if (filters.color && item.color.toLowerCase() !== filters.color.toLowerCase()) return false;
      if (filters.season && item.season !== filters.season) return false;
      if (filters.brand && !item.brand.toLowerCase().includes(filters.brand.toLowerCase())) return false;
      if (filters.search) {
        const q = filters.search.toLowerCase();
        return (
          item.name.toLowerCase().includes(q) ||
          item.brand.toLowerCase().includes(q) ||
          item.color.toLowerCase().includes(q)
        );
      }
      return true;
    });
  },

  incrementWearCount: (id) =>
    set((s) => ({
      items: s.items.map((i) =>
        i.id === id ? { ...i, wearCount: i.wearCount + 1, lastWorn: new Date().toISOString().split('T')[0] } : i,
      ),
    })),
}));
