import * as React from 'react';

/**
 * Tabs — from @smartervote/design-system@0.1.0.
 */
export interface TabsProps {
  items: TabItem[];
  /** Currently selected tab value (controlled). */
  value: string;
  onChange: (value: string) => void;
  style?: React.CSSProperties;
  className?: string;
  id?: string;
  children?: React.ReactNode;
}

export declare const Tabs: React.ComponentType<TabsProps>;
