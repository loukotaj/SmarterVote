import * as React from "react";
import { ElectionCountdown } from "@smartervote/design-system";

export function TwelveDaysOut() {
  const electionDate = new Date(Date.now() + 1000 * 60 * 60 * 24 * 12).toISOString();
  return (
    <div style={{ maxWidth: 720 }}>
      <ElectionCountdown electionDate={electionDate} />
    </div>
  );
}

export function SixWeeksOut() {
  const electionDate = new Date(Date.now() + 1000 * 60 * 60 * 24 * 42).toISOString();
  return (
    <div style={{ maxWidth: 720 }}>
      <ElectionCountdown electionDate={electionDate} />
    </div>
  );
}

export function PollsOpenToday() {
  const electionDate = new Date().toISOString();
  return (
    <div style={{ maxWidth: 720 }}>
      <ElectionCountdown electionDate={electionDate} />
    </div>
  );
}

export function VotingClosed() {
  const electionDate = new Date(Date.now() - 1000 * 60 * 60 * 24 * 21).toISOString();
  return (
    <div style={{ maxWidth: 720 }}>
      <ElectionCountdown electionDate={electionDate} />
    </div>
  );
}
