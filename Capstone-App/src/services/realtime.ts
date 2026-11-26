import { BASE_URL } from '@/services/api';

/** Events the server pushes over /ws (see Capstone_Agents/main.py realtime_socket). */
export type RealtimeEvent =
  | { type: 'ready'; online: string[] }
  | { type: 'presence'; userId: string; online: boolean }
  | { type: 'typing'; conversationId: string; userId: string }
  | { type: 'read'; conversationId: string }
  | { type: 'message'; conversationId: string; message: { id: string; body: string; createdAt: string; mine: boolean; read: boolean } }
  | { type: 'order'; event: 'placed' | 'shipped' | 'completed' | 'cancelled'; orderId: string; productTitle: string }
  | { type: 'pong' }
  | { type: 'error'; detail: string };

type Listener = (event: RealtimeEvent) => void;
type StatusListener = (connected: boolean) => void;

const BACKOFF_MS = [1000, 2000, 5000, 10000, 20000];
const HEARTBEAT_MS = 25000;

function socketUrl() {
  return `${BASE_URL.replace(/^http/i, 'ws')}/ws`;
}

/**
 * One WebSocket per signed-in app. Reconnects with backoff after drops; the session
 * token is sent as the first message (never in the URL, which servers log).
 */
class RealtimeClient {
  private socket: WebSocket | null = null;
  private token: string | null = null;
  private attempt = 0;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private heartbeat: ReturnType<typeof setInterval> | null = null;
  private listeners = new Set<Listener>();
  private statusListeners = new Set<StatusListener>();

  connect(token: string) {
    if (this.token === token && this.socket) return;
    this.disconnect();
    this.token = token;
    this.open();
  }

  disconnect() {
    this.token = null;
    if (this.retryTimer) clearTimeout(this.retryTimer);
    this.retryTimer = null;
    this.stopHeartbeat();
    const socket = this.socket;
    this.socket = null;
    socket?.close(1000);
    this.setStatus(false);
  }

  send(event: Record<string, unknown>) {
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify(event));
  }

  subscribe(listener: Listener) {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  }

  onStatus(listener: StatusListener) {
    this.statusListeners.add(listener);
    return () => { this.statusListeners.delete(listener); };
  }

  private open() {
    const token = this.token;
    if (!token) return;
    let socket: WebSocket;
    try {
      socket = new WebSocket(socketUrl());
    } catch {
      this.scheduleReconnect();
      return;
    }
    this.socket = socket;
    socket.onopen = () => socket.send(JSON.stringify({ type: 'auth', token }));
    socket.onmessage = (message) => {
      let event: RealtimeEvent;
      try {
        event = JSON.parse(String(message.data));
      } catch {
        return;
      }
      if (event.type === 'ready') {
        this.attempt = 0;
        this.startHeartbeat();
        this.setStatus(true);
      }
      if (event.type === 'error') {
        // Bad or expired session: stop retrying until the app signs in again.
        this.token = null;
      }
      this.listeners.forEach((listener) => listener(event));
    };
    socket.onclose = () => {
      if (this.socket !== socket) return; // replaced by a newer connection
      this.socket = null;
      this.stopHeartbeat();
      this.setStatus(false);
      this.scheduleReconnect();
    };
    socket.onerror = () => socket.close();
  }

  private scheduleReconnect() {
    if (!this.token || this.retryTimer) return;
    const delay = BACKOFF_MS[Math.min(this.attempt, BACKOFF_MS.length - 1)];
    this.attempt += 1;
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null;
      this.open();
    }, delay);
  }

  private startHeartbeat() {
    this.stopHeartbeat();
    this.heartbeat = setInterval(() => this.send({ type: 'ping' }), HEARTBEAT_MS);
  }

  private stopHeartbeat() {
    if (this.heartbeat) clearInterval(this.heartbeat);
    this.heartbeat = null;
  }

  private setStatus(connected: boolean) {
    this.statusListeners.forEach((listener) => listener(connected));
  }
}

export const realtime = new RealtimeClient();
