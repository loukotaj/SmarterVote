# Quiz Feature Plan

Status: Proposal. The quiz phase and schema described here are not a current production contract.

## Concept

A per-race quiz (10 questions) that helps voters pick a candidate based on their own values. Questions are generated from observed differences between candidates, so they're specific to the race and grounded in the research pipeline's output.

## Pipeline Stage

Add a new `quiz` phase after the existing research pipeline completes. Input: finished race data with candidate positions on the 12 canonical issues. Output: a static JSON quiz object stored alongside race data in GCS.

### What the quiz generator does

1. For each canonical issue, compare candidate positions across all candidates in the race
2. Select issues where candidates meaningfully differ (skip unknowns and alignments)
3. Generate a question + answer options per issue, framed neutrally (e.g. "On climate policy, which position matches yours?")
4. Aim for 5–10 questions depending on how many real differences exist
5. Include candidate-to-answer mapping so scoring is straightforward client-side

### Output schema (rough)

```json
{
  "race_id": "ga-senate-2026",
  "questions": [
    {
      "issue": "climate",
      "question": "What should be the priority for U.S. energy policy?",
      "options": [
        { "text": "Prioritize domestic fossil fuel production", "candidate_ids": ["candidate-a"] },
        { "text": "Accelerate transition to renewable energy", "candidate_ids": ["candidate-b"] }
      ]
    }
  ]
}
```

## Frontend

- Add a "Take the Quiz" entry point on each race page
- Simple one-question-at-a-time UI, no account required
- Score at the end: show match % per candidate with a top recommendation
- Shareable result card ("I match 80% with [Candidate] on the GA Senate race")

## Cost Profile

Static — generated once per race, served from GCS or bundled into the frontend build. No per-user AI cost. Regenerate only when race data is updated.

## Build Order

1. Quiz generation prompt + output schema
2. New pipeline phase that calls the generator and writes `quizzes/{race_id}.json` to GCS
3. Minimal quiz UI on the race page (no address lookup needed)
4. Result/share screen

## Future: Ballot-Level Quiz

Once per-race quizzes work, roll up all races on a user's ballot via address lookup:
- **Google Civic Information API** (free) maps address → races + candidates
- Run the user through quizzes for all contested races on their ballot
- Produce a full personalized ballot recommendation

This is the high-value version but address lookup adds complexity; ship per-race first.
