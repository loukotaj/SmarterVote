import * as React from 'react';

/**
 * Card — from @smartervote/design-system@0.1.0.
 */
export interface CardProps {
  /** HTML element to render as. Defaults to "div". */
  as?: "symbol" | "object" | "a" | "abbr" | "address" | "area" | "article" | "aside" | "audio" | "b" | "base" | "bdi" | "bdo" | "big" | "blockquote" | "body" | (string & {}) /* +162 more */;
  className?: string;
  id?: string;
  style?: React.CSSProperties;
  children?: React.ReactNode;
}

export declare const Card: React.ComponentType<CardProps>;
