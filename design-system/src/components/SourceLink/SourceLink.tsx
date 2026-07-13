export interface SourceLinkProps {
  /** Source URL. Only http/https URLs render as a link — anything else falls back to plain text. */
  url: string;
  /** Optional source title, used for the label and title-attribute fallback. */
  title?: string;
  /** Explicit label override. Falls back to title, then the URL's domain. */
  text?: string;
}

function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/**
 * Inline external-source citation link — an icon-suffixed underline link
 * that opens in a new tab, with a domain fallback label. Renders as plain
 * text (no link) for any non-http(s) URL.
 */
export function SourceLink({ url, title, text }: SourceLinkProps) {
  const domain = domainOf(url);
  const isSafe = /^https?:\/\//i.test(url.trim());
  const label = text || title || domain;

  if (!isSafe) {
    return <span className="inline-flex items-center gap-1 text-xs sm:text-sm">{label}</span>;
  }

  return (
    <a
      href={url.trim()}
      target="_blank"
      rel="noopener noreferrer"
      title={`${label} - Open in new tab`}
      className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-500 dark:hover:text-blue-400 text-xs sm:text-sm underline"
    >
      <span>{label}</span>
      <svg className="w-3 h-3 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
        />
      </svg>
    </a>
  );
}
