import type { Candidate, IssueKey, Race, Source } from "$lib/types";

const source = (
  url: string,
  title: string,
  type: Source["type"] = "website",
): Source => ({
  url,
  title,
  type,
  last_accessed: "2026-07-11T00:00:00Z",
});

const candidate = (
  name: string,
  party: string,
  summary: string,
  image_url: string,
  issues: Partial<Record<IssueKey, Candidate["issues"][IssueKey]>>,
  incumbent = false,
): Candidate => ({
  name,
  party,
  incumbent,
  summary,
  summary_sources: [],
  image_url,
  issues,
  career_history: [],
  education: [],
  links: [],
  social_media: {},
});

// Compact, public-data fallbacks keep the homepage demo useful in local/CI builds.
// Production replaces these with the current published records for the same IDs.
export const gradeAHomepageFallbacks: Race[] = [
  {
    id: "ak-senate-2026",
    title: "2026 United States Senate Election in Alaska",
    office: "U.S. Senate",
    jurisdiction: "Alaska",
    election_date: "2026-11-03",
    updated_utc: "2026-07-11T21:48:55.094386+00:00",
    generator: [],
    validation_grade: {
      grade: "A",
      score: 92,
      passed: true,
      summary: "Validated by 3/3 reviewers.",
    },
    candidates: [
      candidate(
        "Daniel S. Sullivan",
        "Republican",
        "Incumbent U.S. senator and retired Marine Corps colonel who previously served as Alaska attorney general and natural resources commissioner.",
        "https://upload.wikimedia.org/wikipedia/commons/1/10/Senator_Dan_Sullivan_official.jpg",
        {
          Economy: {
            issue: "Economy",
            stance:
              "Supports targeted federal investment in Alaska infrastructure and energy, paired with permitting reform.",
            confidence: "high",
            sources: [
              source(
                "https://www.sullivan.senate.gov/newsroom/press-releases/sullivan-statement-on-bipartisan-infrastructure-package",
                "Statement on the bipartisan infrastructure package",
                "government",
              ),
            ],
          },
          "Climate/Energy": {
            issue: "Climate/Energy",
            stance:
              "Supports expanded oil, gas, LNG, nuclear, and critical-mineral production alongside technology-led emissions reductions.",
            confidence: "high",
            sources: [
              source(
                "https://www.sullivan.senate.gov/imo/media/doc/EnergyPlan_1Page_020822[web].pdf",
                "Energy plan",
                "pdf",
              ),
            ],
          },
          Healthcare: {
            issue: "Healthcare",
            stance:
              "Backed the 2025 federal budget law and its rural health program, while later supporting an extension of ACA subsidies.",
            confidence: "high",
            sources: [
              source(
                "https://www.congress.gov/bill/119th-congress/house-bill/1",
                "H.R. 1, 119th Congress",
                "government",
              ),
            ],
          },
        },
        true,
      ),
      candidate(
        "Mary Peltola",
        "Democratic",
        "Former U.S. representative and Alaska state legislator; the first Alaska Native member of Congress.",
        "https://upload.wikimedia.org/wikipedia/commons/a/a5/Mary_Peltola_Congressional_Member_Portrait_%282%29.jpeg",
        {
          Economy: {
            issue: "Economy",
            stance:
              "Proposes an affordability agenda including tax relief for working families and expanded family credits.",
            confidence: "high",
            sources: [
              source(
                "https://nativenewsonline.net/currents/mary-peltola-unveils-plan-to-tackle-alaskas-affordability-crisis-in-u-s-senate-campaign/",
                "Peltola affordability plan",
                "news",
              ),
            ],
          },
          "Climate/Energy": {
            issue: "Climate/Energy",
            stance:
              "Balances continued Alaska oil development with clean-energy credits, renewables, and permitting reform.",
            confidence: "high",
            sources: [
              source(
                "https://www.eenews.net/articles/mary-peltolas-delicate-balance-on-energy-climate/",
                "Peltola's approach to energy and climate",
                "news",
              ),
            ],
          },
          Healthcare: {
            issue: "Healthcare",
            stance:
              "Supports extending ACA subsidies and reversing Medicaid reductions as part of an affordability agenda.",
            confidence: "high",
            sources: [
              source(
                "https://thehill.com/policy/healthcare/5870588-alaska-healthcare-sullivan-reelection/",
                "Alaska health-care policy in the Senate race",
                "news",
              ),
            ],
          },
        },
      ),
    ],
  },
  {
    id: "al-governor-2026",
    title: "2026 Alabama Gubernatorial General Election",
    office: "Governor of Alabama",
    jurisdiction: "Alabama",
    election_date: "2026-11-03",
    updated_utc: "2026-06-29T03:53:14.495966+00:00",
    generator: [],
    validation_grade: {
      grade: "A",
      score: 90,
      passed: true,
      summary: "Validated by 3/3 reviewers.",
    },
    candidates: [
      candidate(
        "Tommy Tuberville",
        "Republican",
        "U.S. senator and former college football coach; the 2026 Republican nominee for governor.",
        "https://static.wixstatic.com/media/f28da3_a29ee1e634384e96bd88ece8241f3a8b~mv2.jpg/v1/fill/w_522,h_337,al_c,q_80/tommy-tuberville.jpg",
        {
          Economy: {
            issue: "Economy",
            stance:
              "Advocates lower taxes, less regulation, and policies intended to attract manufacturing and jobs.",
            confidence: "high",
            sources: [
              source(
                "https://www.coachforgovernor.com/issues",
                "Campaign issues",
              ),
            ],
          },
          Healthcare: {
            issue: "Healthcare",
            stance:
              "Supports market-based health-care changes and price transparency while opposing the Affordable Care Act.",
            confidence: "high",
            sources: [
              source(
                "https://www.tuberville.senate.gov/newsroom/press-releases/tuberville-joins-marshall-in-promoting-health-care-pricing-transparency/",
                "Health-care pricing transparency",
                "government",
              ),
            ],
          },
        },
      ),
      candidate(
        "Doug Jones",
        "Democratic",
        "Former U.S. senator and federal prosecutor; the 2026 Democratic nominee for governor.",
        "https://run.imgix.net/f32d6958-d323-4eef-8ba1-2f9bb17c7857/abf7e436-c020-400a-99b4-7221550218ba/abf7e436-c020-400a-99b4-7221550218ba.jpg?auto=compress,format&fit=crop&w=600",
        {
          Economy: {
            issue: "Economy",
            stance:
              "Supports eliminating the grocery tax, targeted tax relief, higher wages, and expanded child-care access.",
            confidence: "high",
            sources: [
              source(
                "https://www.dougjones.com/priorities",
                "Priorities for Alabama",
              ),
            ],
          },
          Healthcare: {
            issue: "Healthcare",
            stance:
              "Supports Medicaid expansion and policies intended to reduce costs for Alabama families.",
            confidence: "high",
            sources: [
              source(
                "https://www.dougjones.com/priorities",
                "Priorities for Alabama",
              ),
            ],
          },
        },
      ),
    ],
  },
];

export const isHomepagePreviewRace = (race: Race) =>
  race.validation_grade?.passed === true && race.validation_grade.score >= 85;

export const mergeHomepagePreviewRaces = (
  verified: Race[],
  limit = 5,
): Race[] => {
  const seen = new Set<string>();
  return verified
    .filter((race) => {
      if (seen.has(race.id)) return false;
      seen.add(race.id);
      return true;
    })
    .slice(0, limit);
};
