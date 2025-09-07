/**
 * WebSocket connection and message handling store
 */
import { writable } from 'svelte/store';
import type { LogEntry } from '$lib/types';

type PipelineEvent =
  | { type: "log"; level: string; message: string; timestamp?: string; run_id?: string }
  | { type: "run_started"; run_id: string; step: string }
  | { type: "run_progress"; progress?: number; message?: string }
  | { type: "run_completed"; result?: unknown; artifact_id?: string; duration_ms?: number }
  | { type: "run_failed"; error?: string }
  | { type: "run_status"; data: { run_id: string; status: string; [key: string]: any } }
  | { type: "buffered_logs"; data: LogEntry[] };

interface WebSocketState {
  ws: WebSocket | null;
  connected: boolean;
  reconnectAttempts: number;
  maxReconnectAttempts: number;
}

const initialState: WebSocketState = {
  ws: null,
  connected: false,
  reconnectAttempts: 0,
  maxReconnectAttempts: 5
};

export const websocketStore = writable<WebSocketState>(initialState);

// Message queue for throttled processing
let messageQueue: PipelineEvent[] = [];
let processingTimer: ReturnType<typeof setTimeout> | null = null;
let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;

// Event handlers - these will be set by the component using the store
let onMessage: ((event: PipelineEvent) => void) | null = null;
let onLog: ((level: string, message: string, timestamp?: string, run_id?: string) => void) | null = null;

export const websocketActions = {
  /**
   * Set event handlers
   */
  setHandlers: (handlers: {
    onMessage?: (event: PipelineEvent) => void;
    onLog?: (level: string, message: string, timestamp?: string, run_id?: string) => void;
  }) => {
    onMessage = handlers.onMessage || null;
    onLog = handlers.onLog || null;
  },

  /**
   * Connect to WebSocket
   */
  connect: (apiBase: string, token: string) => {
    // Clear any existing reconnect timeout
    if (reconnectTimeout) {
      clearTimeout(reconnectTimeout);
      reconnectTimeout = null;
    }

    websocketStore.update(state => {
      // Don't reconnect if we've hit the limit
      if (state.reconnectAttempts >= state.maxReconnectAttempts) {
        onLog?.('error', 'Max WebSocket reconnection attempts reached. Please refresh the page.');
        return state;
      }

      try {
        const wsUrl = apiBase.replace(/^http/, 'ws') + `/ws/logs?token=${encodeURIComponent(token)}`;
        const ws = new WebSocket(wsUrl);

        ws.onopen = () => {
          websocketStore.update(s => ({ ...s, connected: true, reconnectAttempts: 0 }));
          onLog?.('info', 'Connected to pipeline server');
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data) as PipelineEvent;
            queueMessage(data);
          } catch (e) {
            console.error('Failed to parse WebSocket message:', e);
            onLog?.('error', 'Failed to parse server message');
          }
        };

        ws.onclose = (event) => {
          websocketStore.update(s => ({ ...s, connected: false }));
          
          if (event.code === 1000) {
            // Normal closure, don't reconnect
            onLog?.('info', 'WebSocket connection closed normally');
            return;
          }

          onLog?.('warning', 'Disconnected from pipeline server');
          
          websocketStore.update(s => {
            const newAttempts = s.reconnectAttempts + 1;
            
            if (newAttempts < s.maxReconnectAttempts) {
              const delay = Math.min(1000 * Math.pow(2, newAttempts), 10000); // Exponential backoff, max 10s
              onLog?.('info', `Attempting to reconnect in ${delay/1000}s... (${newAttempts}/${s.maxReconnectAttempts})`);
              
              reconnectTimeout = setTimeout(() => {
                websocketActions.connect(apiBase, token);
              }, delay);
            }
            
            return { ...s, reconnectAttempts: newAttempts };
          });
        };

        ws.onerror = (error) => {
          websocketStore.update(s => ({ ...s, connected: false }));
          console.error('WebSocket error:', error);
          onLog?.('error', 'WebSocket connection error');
        };

        return { ...state, ws };
      } catch (error) {
        console.error('Failed to create WebSocket:', error);
        onLog?.('error', 'Failed to create WebSocket connection');
        return state;
      }
    });
  },

  /**
   * Disconnect WebSocket
   */
  disconnect: () => {
    websocketStore.update(state => {
      if (state.ws) {
        state.ws.close(1000, 'Component unmounting');
      }
      return { ...state, ws: null, connected: false };
    });

    // Clear reconnection timeout
    if (reconnectTimeout) {
      clearTimeout(reconnectTimeout);
      reconnectTimeout = null;
    }

    // Clear message processing timer
    if (processingTimer) {
      clearTimeout(processingTimer);
      processingTimer = null;
    }
  },

  /**
   * Send message to WebSocket
   */
  send: (message: any) => {
    websocketStore.subscribe(state => {
      if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify(message));
      }
    })();
  }
};

/**
 * Queue message for throttled processing
 */
function queueMessage(message: PipelineEvent) {
  messageQueue.push(message);

  // Start processing if not already running
  if (!processingTimer) {
    processingTimer = setTimeout(processMessageQueue, 10);
  }
}

/**
 * Process message queue in batches
 */
function processMessageQueue() {
  if (messageQueue.length === 0) return;

  // Process up to 5 messages at once to prevent blocking
  const messagesToProcess = messageQueue.splice(0, 5);

  for (const message of messagesToProcess) {
    handleMessage(message);
  }

  // If there are more messages, schedule next batch
  if (messageQueue.length > 0) {
    processingTimer = setTimeout(processMessageQueue, 10);
  } else {
    processingTimer = null;
  }
}

/**
 * Handle individual WebSocket message
 */
function handleMessage(data: PipelineEvent) {
  // Handle log messages specifically
  if (data.type === 'log') {
    onLog?.(data.level, data.message, data.timestamp, data.run_id);
  }

  // Forward all messages to the general handler
  onMessage?.(data);
}