/**
 * Pipeline utility functions
 */
import type { RunStatus } from '$lib/types';

/**
 * Format duration in seconds to human readable format
 */
export function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
}

/**
 * Get CSS class for run status
 */
export function getStatusClass(status: RunStatus | string): string {
  switch (status) {
    case "running":
      return "bg-blue-100 text-blue-800 border-blue-200";
    case "completed":
      return "bg-green-100 text-green-800 border-green-200";
    case "failed":
      return "bg-red-100 text-red-800 border-red-200";
    default:
      return "bg-gray-100 text-gray-800 border-gray-200";
  }
}

/**
 * Get CSS class for log level
 */
export function getLogClass(level: string): string {
  switch (level) {
    case "error":
      return "bg-red-50 text-red-800 border-l-red-500";
    case "warning":
      return "bg-yellow-50 text-yellow-800 border-l-yellow-500";
    case "info":
      return "bg-blue-50 text-blue-800 border-l-blue-500";
    case "debug":
      return "bg-gray-50 text-gray-600 border-l-gray-400";
    default:
      return "bg-gray-50 text-gray-600 border-l-gray-400";
  }
}

/**
 * Safely stringify JSON with size limits and error handling
 */
export function safeJsonStringify(
  data: unknown, 
  maxSize: number = 500000,
  indent: number = 2
): { content: string; truncated: boolean; error?: string } {
  if (data === null || data === undefined) {
    return { content: '', truncated: false };
  }

  try {
    // Quick size check for objects
    if (typeof data === 'object' && data !== null) {
      const keys = Object.keys(data);
      if (keys.length > 1000) {
        return {
          content: `[LARGE OBJECT DETECTED]\nObject has ${keys.length} top-level keys\nType: ${typeof data}`,
          truncated: true
        };
      }
    }

    const jsonString = JSON.stringify(data, null, indent);

    if (jsonString.length > maxSize) {
      const truncated = jsonString.substring(0, maxSize);
      const sizeMB = (jsonString.length / 1024 / 1024).toFixed(1);
      return {
        content: `${truncated}\n\n... [TRUNCATED - Content too large]\n... Full size: ${sizeMB}MB`,
        truncated: true
      };
    }

    return { content: jsonString, truncated: false };
  } catch (error) {
    console.error('Failed to stringify data:', error);

    // Provide helpful info about the object
    if (typeof data === 'object' && data !== null) {
      const keys = Object.keys(data);
      return {
        content: `[ERROR: Unable to display content]\nReason: ${error}\nType: ${typeof data}\nKeys: ${keys.length > 10 ? keys.slice(0, 10).join(', ') + '...' : keys.join(', ')}`,
        truncated: false,
        error: String(error)
      };
    }

    return {
      content: `[ERROR: Unable to display content]\nReason: ${error}\nType: ${typeof data}`,
      truncated: false,
      error: String(error)
    };
  }
}

/**
 * Copy text to clipboard with size validation
 */
export async function copyToClipboard(text: string, maxSize: number = 5000000): Promise<boolean> {
  try {
    // Check size before copying (Chrome has ~5MB clipboard limit)
    if (text.length > maxSize) {
      console.warn(`Content too large to copy (${(text.length / 1024 / 1024).toFixed(1)}MB)`);
      return false;
    }

    await navigator.clipboard.writeText(text);
    return true;
  } catch (error) {
    console.error('Failed to copy to clipboard:', error);
    return false;
  }
}

/**
 * Download data as JSON file
 */
export function downloadAsJson(data: unknown, filename?: string): boolean {
  try {
    const jsonString = JSON.stringify(data, null, 2);
    const blob = new Blob([jsonString], { type: 'application/json' });
    
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || `pipeline-result-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
    
    return true;
  } catch (error) {
    console.error('Failed to download file:', error);
    return false;
  }
}

/**
 * Validate JSON string
 */
export function validateJson(jsonString: string): { valid: boolean; error?: string; data?: unknown } {
  try {
    const data = JSON.parse(jsonString);
    return { valid: true, data };
  } catch (error) {
    return { valid: false, error: String(error) };
  }
}

/**
 * Debounce function for API calls
 */
export function debounce<T extends (...args: any[]) => any>(
  func: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeoutId: ReturnType<typeof setTimeout> | null = null;
  
  return (...args: Parameters<T>) => {
    if (timeoutId) clearTimeout(timeoutId);
    timeoutId = setTimeout(() => func(...args), wait);
  };
}

/**
 * Throttle function for frequent updates
 */
export function throttle<T extends (...args: any[]) => any>(
  func: T,
  limit: number
): (...args: Parameters<T>) => void {
  let inThrottle = false;
  
  return (...args: Parameters<T>) => {
    if (!inThrottle) {
      func(...args);
      inThrottle = true;
      setTimeout(() => inThrottle = false, limit);
    }
  };
}