# Claude marketing examples

Use these templates as the first choice for branded assets. Keep factual copy concise, do not invent polling or
candidate positions, and include a source note when an asset summarizes research.

## Social announcement

```tsx
<SocialAnnouncement
  format="square"
  title="Arizona Senate research is ready"
  subtitle="Compare sourced candidate records before Election Day."
  callout="New race guide"
  highlights={["Candidate biographies", "Issue-by-issue positions", "Finance and voting records"]}
/>
```

## Candidate comparison

```tsx
<CandidateComparisonGraphic
  format="landscape"
  title="Where the candidates stand"
  issue="Healthcare"
  candidates={candidateSummaries}
  sourceNote="Condensed from cited SmarterVote research. Read the full sources at smartervote.org."
/>
```

## Campaign update

```tsx
<CampaignUpdate
  title="SmarterVote monthly update"
  subtitle="Transparent voter research, built in public."
  metrics={[{ value: "24", label: "Race guides" }, { value: "96", label: "Candidates researched" }]}
  update="This month we expanded race coverage and strengthened automated source validation."
/>
```

## Research report cover

```tsx
<ResearchReportCover
  title="2026 Arizona Senate voter research"
  subtitle="Candidate backgrounds, issue positions, campaign finance, and cited public records."
  electionDate="November 3, 2026"
  preparedFor="Arizona voters"
  topics={["Candidate research", "Issue comparison", "Source review"]}
/>
```
