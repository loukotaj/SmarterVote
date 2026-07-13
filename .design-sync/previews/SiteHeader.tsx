import * as React from "react";
import { SiteHeader } from "@smartervote/design-system";

const navLinks = [
  { href: "/elections/", label: "Elections", active: true },
  { href: "/about/", label: "About" },
  { href: "/support/", label: "Support" },
  { href: "/ballot/", label: "My Ballot" },
  { href: "/forecast/", label: "Forecast" },
];

/** Sticky header with an empty search box and the light/dark toggle. */
export function EmptySearch() {
  return (
    <div style={{ width: 680 }}>
      <SiteHeader links={navLinks} searchValue="" />
    </div>
  );
}

/** Search box populated with a query and a composed results dropdown (Elections + Candidates groups). */
export function SearchWithResults() {
  const results = (
    <>
      <div className="px-4 pb-1 pt-2 text-xs font-semibold uppercase tracking-wide text-content-subtle">Elections</div>
      <a href="/races/ga-senate-2026/" className="block px-4 py-2 text-sm text-content hover:bg-surface-alt">
        Georgia U.S. Senate — 2026
      </a>
      <a href="/races/nc-senate-2026/" className="block px-4 py-2 text-sm text-content hover:bg-surface-alt">
        North Carolina U.S. Senate — 2026
      </a>
      <div className="px-4 pb-1 pt-3 text-xs font-semibold uppercase tracking-wide text-content-subtle">Candidates</div>
      <a href="/races/ga-senate-2026/alice-johnson" className="block px-4 py-2 text-sm text-content hover:bg-surface-alt">
        Alice Johnson <span className="text-content-subtle">— GA Senate</span>
      </a>
      <a href="/races/nc-senate-2026/ethan-brooks" className="block px-4 py-2 text-sm text-content hover:bg-surface-alt">
        Ethan Brooks <span className="text-content-subtle">— NC Senate</span>
      </a>
    </>
  );

  return (
    <div style={{ width: 680 }}>
      <SiteHeader links={navLinks} searchValue="senate" searchResults={results} />
    </div>
  );
}
