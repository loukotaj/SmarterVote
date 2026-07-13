import * as React from "react";

export interface SiteHeaderLink {
  href: string;
  label: string;
  active?: boolean;
}

export interface SiteHeaderProps {
  links: SiteHeaderLink[];
  darkMode?: boolean;
  onToggleDark?: () => void;
  searchPlaceholder?: string;
  searchValue?: string;
  onSearchChange?: (value: string) => void;
  /** Rendered below the search box when non-empty — the results dropdown
   * (Elections/Candidates groups). Left as a slot so the design agent can
   * compose whatever result list a given mockup needs. */
  searchResults?: React.ReactNode;
}

/**
 * Sticky translucent site header — wordmark, primary nav, a pill search
 * box, and the light/dark toggle. The live autocomplete dropdown behind
 * search is app-specific routing logic (not ported); pass `searchResults`
 * to compose one.
 */
export function SiteHeader({
  links,
  darkMode = false,
  onToggleDark,
  searchPlaceholder = "Search elections or candidates",
  searchValue,
  onSearchChange,
  searchResults,
}: SiteHeaderProps) {
  return (
    <header className="sticky top-0 z-50 bg-surface/90 backdrop-blur-md shadow-sm border-b border-stroke/50">
      <div className="container mx-auto max-w-7xl px-4 py-3">
        <div className="flex flex-wrap items-center gap-3 lg:flex-nowrap">
          <a href="/" className="mr-auto text-xl sm:text-2xl font-bold text-blue-600 hover:text-blue-700 whitespace-nowrap" aria-label="Smarter.Vote home">
            Smarter.Vote
          </a>

          <nav
            className="order-3 flex w-full items-center gap-x-4 gap-y-2 overflow-x-auto text-sm lg:order-none lg:w-auto"
            aria-label="Primary navigation"
          >
            {links.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className={`whitespace-nowrap text-content-muted hover:text-content ${link.active ? "font-semibold" : ""}`}
              >
                {link.label}
              </a>
            ))}
          </nav>

          <div className="relative order-2 w-full sm:order-none sm:w-64 lg:w-72">
            <label className="sr-only" htmlFor="site-search">
              Search elections and candidates
            </label>
            <input
              id="site-search"
              value={searchValue}
              onChange={(e) => onSearchChange?.(e.target.value)}
              autoComplete="off"
              placeholder={searchPlaceholder}
              className="w-full rounded-full border border-stroke bg-surface-alt py-2 pl-4 pr-9 text-sm text-content focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            {searchValue && (
              <button type="button" aria-label="Clear search" className="absolute inset-y-0 right-0 px-3 text-content-subtle hover:text-content">
                ×
              </button>
            )}

            {searchResults && (
              <div className="absolute left-0 right-0 top-full mt-2 max-h-96 overflow-y-auto rounded-xl border border-stroke bg-surface py-2 shadow-xl" role="listbox">
                {searchResults}
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={onToggleDark}
            aria-label={darkMode ? "Switch to light mode" : "Switch to dark mode"}
            className="rounded-lg p-2 text-content-subtle hover:bg-surface-alt hover:text-content"
          >
            {darkMode ? "☀" : "☾"}
          </button>
        </div>
      </div>
    </header>
  );
}
