import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useToastStore } from '@/components/ui/Toast';
import { realtime, type RealtimeEvent } from '@/services/realtime';
import { useAuthStore } from '@/store/authStore';
import { useRealtimeStore } from '@/store/realtimeStore';
import type { Conversation, MarketMessage } from '@/types';

type Thread = { conversation: Conversation; messages: MarketMessage[] };

const ORDER_TOASTS = {
  placed: (title: string) => `New order: someone bought “${title}”`,
  shipped: (title: string) => `“${title}” has been shipped`,
  completed: (title: string) => `The buyer received “${title}”`,
  cancelled: (title: string) => `The order for “${title}” was cancelled`,
} as const;

/**
 * Keeps the app's WebSocket open while signed in and applies pushed events directly
 * to the React Query cache, so chats, badges and orders update instantly. Mount once.
 */
export function useRealtime() {
  const token = useAuthStore((s) => s.token);
  const queryClient = useQueryClient();
  const showToast = useToastStore((s) => s.show);

  useEffect(() => {
    if (!token) return undefined;
    const store = useRealtimeStore.getState();
    let wasConnected = false;

    const stopStatus = realtime.onStatus((connected) => {
      store.setConnected(connected);
      if (connected && wasConnected === false) {
        // (Re)connected: catch up on anything missed while offline.
        void queryClient.invalidateQueries({ queryKey: ['conversations'] });
        void queryClient.invalidateQueries({ queryKey: ['conversation'] });
      }
      wasConnected = connected;
    });

    const stopEvents = realtime.subscribe((event: RealtimeEvent) => {
      switch (event.type) {
        case 'ready':
          store.setOnline(event.online);
          break;
        case 'presence':
          store.setPresence(event.userId, event.online);
          break;
        case 'typing':
          store.markTyping(event.conversationId);
          break;
        case 'message': {
          store.clearTyping(event.conversationId);
          queryClient.setQueryData<Thread>(['conversation', event.conversationId], (thread) => {
            if (!thread || thread.messages.some((m) => m.id === event.message.id)) return thread;
            return { ...thread, messages: [...thread.messages, event.message] };
          });
          void queryClient.invalidateQueries({ queryKey: ['conversations'] });
          break;
        }
        case 'read':
          queryClient.setQueryData<Thread>(['conversation', event.conversationId], (thread) => thread && {
            ...thread,
            messages: thread.messages.map((m) => (m.mine ? { ...m, read: true } : m)),
          });
          break;
        case 'order':
          for (const key of ['seller-dashboard', 'my-orders', 'products', 'product']) {
            void queryClient.invalidateQueries({ queryKey: [key] });
          }
          showToast(ORDER_TOASTS[event.event](event.productTitle), event.event === 'cancelled' ? 'info' : 'success');
          break;
        default:
          break;
      }
    });

    realtime.connect(token);
    return () => {
      stopEvents();
      stopStatus();
      realtime.disconnect();
    };
  }, [token, queryClient, showToast]);
}

/** Tell the other person you're typing (throttled to one event every 2 seconds). */
let lastTypingSent = 0;
export function sendTyping(conversationId: string) {
  const now = Date.now();
  if (now - lastTypingSent < 2000) return;
  lastTypingSent = now;
  realtime.send({ type: 'typing', conversationId });
}
