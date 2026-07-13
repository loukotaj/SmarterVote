import * as React from "react";
import { Avatar } from "@smartervote/design-system";

export function Default() {
  return <Avatar name="Alice Johnson" />;
}

export function Sizes() {
  return (
    <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
      <Avatar name="Bob Lee" size="sm" />
      <Avatar name="Bob Lee" size="md" />
      <Avatar name="Bob Lee" size="lg" />
    </div>
  );
}

export function WithPhoto() {
  return (
    <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
      <Avatar name="Maria Alvarez" src="https://images.unsplash.com/photo-1580489944761-15a19d654956?w=128&h=128&fit=crop&crop=faces" size="md" />
      <Avatar name="Maria Alvarez" src="https://images.unsplash.com/photo-1580489944761-15a19d654956?w=128&h=128&fit=crop&crop=faces" size="lg" />
    </div>
  );
}

export function InitialsVariety() {
  return (
    <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
      <Avatar name="Cheryl Nguyen" size="md" />
      <Avatar name="Desmond O'Brien-Walsh" size="md" />
      <Avatar name="Priya" size="md" />
    </div>
  );
}

export function CandidateRosterRow() {
  return (
    <div style={{ display: "flex", gap: 24 }}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
        <Avatar name="Alice Johnson" size="lg" className="ring-2 ring-blue-500 ring-offset-2" />
        <span style={{ fontSize: 12, color: "#4b5563" }}>Alice Johnson (D)</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
        <Avatar name="Bob Lee" size="lg" className="ring-2 ring-red-500 ring-offset-2" />
        <span style={{ fontSize: 12, color: "#4b5563" }}>Bob Lee (R)</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
        <Avatar name="Sam Okafor" size="lg" className="ring-2 ring-gray-400 ring-offset-2" />
        <span style={{ fontSize: 12, color: "#4b5563" }}>Sam Okafor (I)</span>
      </div>
    </div>
  );
}
