import * as React from "react";
import { SectionHeader } from "@smartervote/design-system";

export function WithEyebrowAndDescription() {
  return (
    <div style={{ maxWidth: 640 }}>
      <SectionHeader
        eyebrow="Smarter.Vote"
        title="Our Methodology"
        description="How we research candidates, verify sources, and generate AI-reviewed race profiles for every U.S. election."
      />
    </div>
  );
}

export function PolicyPage() {
  return (
    <div style={{ maxWidth: 640 }}>
      <SectionHeader
        eyebrow="Smarter.Vote"
        title="Privacy Policy"
        description="Last updated June 2026. This policy explains what data we collect, how we use it, and the choices you have."
      />
    </div>
  );
}

export function TitleOnly() {
  return (
    <div style={{ maxWidth: 640 }}>
      <SectionHeader title="Frequently Asked Questions" />
    </div>
  );
}

export function SectionIntro() {
  return (
    <div style={{ maxWidth: 640 }}>
      <SectionHeader
        eyebrow="Georgia Senate 2026"
        title="Where the Candidates Stand"
        description="A side-by-side comparison of each candidate's positions across twelve key issues, sourced from public statements and voting records."
      />
    </div>
  );
}

export function DarkBackground() {
  return (
    <div className="dark" style={{ background: "#030712", padding: 24, borderRadius: 12, maxWidth: 640 }}>
      <SectionHeader
        eyebrow="Smarter.Vote"
        title="Our Methodology"
        description="How we research candidates, verify sources, and generate AI-reviewed race profiles for every U.S. election."
      />
    </div>
  );
}
