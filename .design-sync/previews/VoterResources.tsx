import * as React from "react";
import { VoterResources } from "@smartervote/design-system";

export function AllResourcesWithForecast() {
  return (
    <div style={{ maxWidth: 720, padding: 4 }}>
      <VoterResources
        ballotpediaUrl="https://ballotpedia.org/Georgia_United_States_Senate_election,_2026"
        registerToVoteUrl="https://vote.gov/register"
        howToVoteUrl="https://vote.gov/"
        hasForecast
      />
    </div>
  );
}

export function DefaultsOnlyNoForecast() {
  return (
    <div style={{ maxWidth: 720, padding: 4 }}>
      <VoterResources />
    </div>
  );
}
