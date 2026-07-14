import * as React from "react";
import { Card } from "@smartervote/design-system";

export function Default() {
  return (
    <div style={{ maxWidth: 360 }}>
      <Card style={{ padding: 20 }}>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: "#111827" }}>Georgia U.S. Senate</h3>
        <p style={{ margin: "6px 0 0", fontSize: 14, color: "#4b5563" }}>
          2026 general election — 3 candidates researched, forecast updated 2 hours ago.
        </p>
      </Card>
    </div>
  );
}

export function HeaderAndBody() {
  return (
    <div style={{ maxWidth: 380 }}>
      <Card>
        <div style={{ padding: "14px 20px", borderBottom: "1px solid #e5e7eb" }}>
          <span style={{ fontSize: 12, fontWeight: 700, letterSpacing: "0.05em", textTransform: "uppercase", color: "#2563eb" }}>
            Senate
          </span>
        </div>
        <div style={{ padding: 20 }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: "#111827" }}>Alice Johnson vs. Bob Lee</h3>
          <p style={{ margin: "8px 0 0", fontSize: 14, color: "#4b5563" }}>
            Both candidates have staked out positions on healthcare access and rural broadband expansion ahead of
            the November election.
          </p>
        </div>
      </Card>
    </div>
  );
}

export function AsArticle() {
  return (
    <div style={{ maxWidth: 360 }}>
      <Card as="article" style={{ padding: 20 }}>
        <p style={{ margin: 0, fontSize: 13, color: "#6b7280" }}>Race summary</p>
        <h3 style={{ margin: "4px 0 0", fontSize: 16, fontWeight: 600, color: "#111827" }}>Michigan Governor 2026</h3>
      </Card>
    </div>
  );
}

export function CompactListItems() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, maxWidth: 340 }}>
      <Card style={{ padding: "12px 16px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: 14, fontWeight: 500, color: "#111827" }}>Georgia U.S. Senate</span>
        <span style={{ fontSize: 12, color: "#6b7280" }}>112 days left</span>
      </Card>
      <Card style={{ padding: "12px 16px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: 14, fontWeight: 500, color: "#111827" }}>Ohio 3rd Congressional District</span>
        <span style={{ fontSize: 12, color: "#6b7280" }}>112 days left</span>
      </Card>
    </div>
  );
}
