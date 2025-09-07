import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock WebSocket and related browser APIs
const mockWebSocket = vi.fn();
Object.defineProperty(globalThis, 'WebSocket', {
  value: mockWebSocket,
});

Object.defineProperty(globalThis, 'requestIdleCallback', {
  value: vi.fn((cb: () => void) => setTimeout(cb, 0)),
});

Object.defineProperty(globalThis, 'requestAnimationFrame', {
  value: vi.fn((cb: () => void) => setTimeout(cb, 0)),
});

// Mock fetch
globalThis.fetch = vi.fn();

describe('Pipeline Auto-refresh Functionality', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('should implement debounced refresh to prevent excessive API calls', async () => {
    const mockLoadRunHistory = vi.fn().mockResolvedValue(undefined);
    const mockLoadArtifacts = vi.fn().mockResolvedValue(undefined);
    
    // Simulate the debounced refresh logic
    const MIN_REFRESH_INTERVAL = 2000;
    let lastRefreshTime = 0;
    let pendingRefresh = false;
    
    const debouncedRefresh = (() => {
      let timeoutId: ReturnType<typeof setTimeout> | null = null;
      
      return async function() {
        if (pendingRefresh) return;
        
        const now = Date.now();
        const timeSinceLastRefresh = now - lastRefreshTime;
        
        if (timeSinceLastRefresh < MIN_REFRESH_INTERVAL) {
          if (timeoutId) clearTimeout(timeoutId);
          timeoutId = setTimeout(debouncedRefresh, MIN_REFRESH_INTERVAL - timeSinceLastRefresh);
          return;
        }
        
        pendingRefresh = true;
        lastRefreshTime = now;
        
        try {
          await Promise.allSettled([mockLoadRunHistory(), mockLoadArtifacts()]);
        } finally {
          pendingRefresh = false;
        }
      };
    })();

    // Test that multiple rapid calls only result in one actual API call
    debouncedRefresh();
    debouncedRefresh();
    debouncedRefresh();
    
    // Wait for debounce period and promises to resolve
    await vi.advanceTimersByTimeAsync(2100);
    
    // Should have triggered API calls only once, despite multiple calls
    expect(mockLoadRunHistory).toHaveBeenCalledTimes(1);
    expect(mockLoadArtifacts).toHaveBeenCalledTimes(1);
  });

  it('should queue WebSocket messages to prevent UI blocking', () => {
    const mockHandleMessage = vi.fn();
    
    // Simulate message queue functionality
    let wsMessageQueue: any[] = [];
    let wsProcessingTimer: ReturnType<typeof setTimeout> | null = null;
    
    function processMessageQueue() {
      if (wsMessageQueue.length === 0) return;
      
      const messagesToProcess = wsMessageQueue.splice(0, 5);
      
      for (const message of messagesToProcess) {
        mockHandleMessage(message);
      }
      
      if (wsMessageQueue.length > 0) {
        wsProcessingTimer = setTimeout(processMessageQueue, 10);
      } else {
        wsProcessingTimer = null;
      }
    }
    
    function queueWebSocketMessage(message: any) {
      wsMessageQueue.push(message);
      
      if (!wsProcessingTimer) {
        wsProcessingTimer = setTimeout(processMessageQueue, 10);
      }
    }

    // Queue multiple messages rapidly
    for (let i = 0; i < 12; i++) {
      queueWebSocketMessage({ type: 'log', message: `Test message ${i}` });
    }
    
    expect(wsMessageQueue).toHaveLength(12);
    expect(mockHandleMessage).not.toHaveBeenCalled();
    
    // Process first batch
    vi.advanceTimersByTime(10);
    expect(mockHandleMessage).toHaveBeenCalledTimes(5);
    expect(wsMessageQueue).toHaveLength(7);
    
    // Process second batch
    vi.advanceTimersByTime(10);
    expect(mockHandleMessage).toHaveBeenCalledTimes(10);
    expect(wsMessageQueue).toHaveLength(2);
    
    // Process final batch
    vi.advanceTimersByTime(10);
    expect(mockHandleMessage).toHaveBeenCalledTimes(12);
    expect(wsMessageQueue).toHaveLength(0);
  });

  it('should handle auto-refresh timer lifecycle correctly', () => {
    let autoRefreshTimer: ReturnType<typeof setInterval> | null = null;
    let isExecuting = false;
    let selectedRun: any = null;
    
    const mockDebouncedRefresh = vi.fn();
    
    function startAutoRefresh() {
      if (autoRefreshTimer) return;
      
      autoRefreshTimer = setInterval(async () => {
        if (isExecuting || (selectedRun && selectedRun.status === "running")) {
          await mockDebouncedRefresh();
        }
      }, 5000);
    }
    
    function stopAutoRefresh() {
      if (autoRefreshTimer) {
        clearInterval(autoRefreshTimer);
        autoRefreshTimer = null;
      }
    }

    // Should not start if already running
    startAutoRefresh();
    const firstTimer = autoRefreshTimer;
    startAutoRefresh();
    expect(autoRefreshTimer).toBe(firstTimer);
    
    // Should refresh when executing
    isExecuting = true;
    vi.advanceTimersByTime(5000);
    expect(mockDebouncedRefresh).toHaveBeenCalledTimes(1);
    
    // Should refresh when run is active
    isExecuting = false;
    selectedRun = { status: "running" };
    vi.advanceTimersByTime(5000);
    expect(mockDebouncedRefresh).toHaveBeenCalledTimes(2);
    
    // Should not refresh when idle
    selectedRun = { status: "completed" };
    vi.advanceTimersByTime(5000);
    expect(mockDebouncedRefresh).toHaveBeenCalledTimes(2);
    
    // Should stop correctly
    stopAutoRefresh();
    expect(autoRefreshTimer).toBe(null);
  });

  it('should use requestIdleCallback for non-blocking JSON processing', () => {
    const mockRequestIdleCallback = vi.mocked(globalThis.requestIdleCallback);
    
    // Simulate the pattern used in selectRun
    const largePayload = { data: 'x'.repeat(200000) }; // Large data
    
    function processPayloadNonBlocking(payload: any) {
      requestIdleCallback(() => {
        try {
          const jsonString = JSON.stringify(payload, null, 2);
          // Process the JSON...
        } catch (error) {
          console.error('Failed to process payload:', error);
        }
      }, { timeout: 3000 });
    }
    
    processPayloadNonBlocking(largePayload);
    
    expect(mockRequestIdleCallback).toHaveBeenCalledWith(
      expect.any(Function),
      { timeout: 3000 }
    );
  });
});