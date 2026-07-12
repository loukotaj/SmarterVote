// Curated from the published ak-senate-2026 record through the Smarter.Vote MCP.
// Keep this compact fallback synchronized when the featured record materially changes.
export const homepageResearchPreview = {
  id: "ak-senate-2026",
  title: "2026 United States Senate Election in Alaska",
  updatedUtc: "2026-07-11T21:48:55.094386+00:00",
  grade: "A",
  score: 92,
  candidates: [
    {
      name: "Daniel S. Sullivan",
      party: "Republican",
      imageUrl:
        "https://upload.wikimedia.org/wikipedia/commons/1/10/Senator_Dan_Sullivan_official.jpg",
      issues: {
        Economy: {
          stance:
            "Supports targeted federal investment in Alaska infrastructure and energy, paired with permitting reform.",
          sources: 2,
        },
        "Climate/Energy": {
          stance:
            "Supports expanded oil, gas, LNG, nuclear, and critical-mineral production alongside technology-led emissions reductions.",
          sources: 2,
        },
        "Abortion & Reproductive Health": {
          stance:
            "Supports anti-abortion policies and state authority over abortion regulation after Dobbs.",
          sources: 2,
        },
      },
    },
    {
      name: "Mary Peltola",
      party: "Democratic",
      imageUrl:
        "https://upload.wikimedia.org/wikipedia/commons/a/a5/Mary_Peltola_Congressional_Member_Portrait_%282%29.jpeg",
      issues: {
        Economy: {
          stance:
            "Proposes an affordability agenda including lower federal income taxes for earners under $92,000 and expanded family credits.",
          sources: 2,
        },
        "Climate/Energy": {
          stance:
            "Balances continued Alaska oil development with clean-energy credits, renewables, and permitting reform.",
          sources: 2,
        },
        "Abortion & Reproductive Health": {
          stance:
            "Opposes a national abortion ban and supports codifying Roe, IVF access, and broader reproductive-health funding.",
          sources: 2,
        },
      },
    },
  ],
} as const;
