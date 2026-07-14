import * as React from "react";
import { SiteFooter } from "@smartervote/design-system";

/** Standard footer nav with the default AI-disclosure notice. */
export function Default() {
  return (
    <div style={{ width: 900 }}>
      <SiteFooter
        links={[
          { href: "/elections/", label: "Elections" },
          { href: "/about/", label: "About" },
          { href: "/support/", label: "Support" },
          { href: "/methodology/", label: "Methodology" },
        ]}
      />
    </div>
  );
}

/** Footer nav including an external link (opens in a new tab). */
export function WithExternalLink() {
  return (
    <div style={{ width: 900 }}>
      <SiteFooter
        links={[
          { href: "/elections/", label: "Elections" },
          { href: "/about/", label: "About" },
          { href: "/support/", label: "Support" },
          { href: "https://github.com/smartervote", label: "Source on GitHub", external: true },
        ]}
      />
    </div>
  );
}
