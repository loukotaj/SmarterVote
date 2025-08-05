import type { Race, Source, SourceType } from "./types";

/**
 * Helper function to create Source objects from standardized source strings
 */
function createSource(sourceString: string): Source {
  const parts = sourceString.split(':');
  const type = parts[1];
  const id = parts[2] || 'unknown';
  
  // Map source types to proper SourceType and generate realistic URLs
  const sourceTypeMap: Record<string, { type: SourceType; baseUrl: string; title: string }> = {
    'voting-record': { type: 'government', baseUrl: 'https://www.congress.gov/member', title: 'Congressional Voting Record' },
    'speech': { type: 'government', baseUrl: 'https://www.congress.gov/congressional-record', title: 'Congressional Speech' },
    'website': { type: 'website', baseUrl: 'https://example.com/candidate', title: 'Official Website' },
    'committee': { type: 'government', baseUrl: 'https://www.congress.gov/committees', title: 'Committee Record' },
    'op-ed': { type: 'news', baseUrl: 'https://example.com/news', title: 'Opinion Editorial' },
    'statement': { type: 'government', baseUrl: 'https://example.com/statements', title: 'Official Statement' },
    'bill': { type: 'government', baseUrl: 'https://www.congress.gov/bill', title: 'Congressional Bill' },
    'interview': { type: 'news', baseUrl: 'https://example.com/interviews', title: 'News Interview' },
    'cosponsorship': { type: 'government', baseUrl: 'https://www.congress.gov/bill', title: 'Bill Cosponsorship' },
    'nra-rating': { type: 'website', baseUrl: 'https://www.nrapvf.org/grades', title: 'NRA Rating' },
    'hearing': { type: 'government', baseUrl: 'https://www.congress.gov/committees', title: 'Congressional Hearing' },
    'town-hall': { type: 'government', baseUrl: 'https://example.com/events', title: 'Town Hall Meeting' },
    'rally': { type: 'government', baseUrl: 'https://example.com/events', title: 'Political Rally' },
    'green-new-deal': { type: 'government', baseUrl: 'https://www.congress.gov/bill', title: 'Green New Deal' },
    'border-visit': { type: 'government', baseUrl: 'https://example.com/visits', title: 'Border Visit Report' },
    'press-conference': { type: 'news', baseUrl: 'https://example.com/press', title: 'Press Conference' },
    'march': { type: 'government', baseUrl: 'https://example.com/events', title: 'Political March' },
    'nea-endorsement': { type: 'website', baseUrl: 'https://www.nea.org/endorsements', title: 'NEA Endorsement' },
    'brady-campaign': { type: 'website', baseUrl: 'https://www.bradyunited.org', title: 'Brady Campaign' },
    'planned-parenthood': { type: 'website', baseUrl: 'https://www.plannedparenthood.org', title: 'Planned Parenthood' },
    'fec': { type: 'government', baseUrl: 'https://www.fec.gov/data/receipts', title: 'FEC Filing' },
    'policy-paper': { type: 'website', baseUrl: 'https://example.com/policy', title: 'Policy Paper' },
    'debate': { type: 'news', baseUrl: 'https://example.com/debates', title: 'Candidate Debate' },
    'endorsement': { type: 'website', baseUrl: 'https://example.com/endorsements', title: 'Organization Endorsement' },
    'forum': { type: 'government', baseUrl: 'https://example.com/forums', title: 'Candidate Forum' },
    'military-service': { type: 'government', baseUrl: 'https://example.com/military', title: 'Military Service Record' },
    'business-background': { type: 'website', baseUrl: 'https://example.com/business', title: 'Business Background' },
    'veterans-forum': { type: 'government', baseUrl: 'https://example.com/veterans', title: 'Veterans Forum' },
    'education-forum': { type: 'government', baseUrl: 'https://example.com/education', title: 'Education Forum' },
    'military-background': { type: 'government', baseUrl: 'https://example.com/military', title: 'Military Background' },
    'floor-speech': { type: 'government', baseUrl: 'https://www.congress.gov/congressional-record', title: 'Floor Speech' },
    'vote': { type: 'government', baseUrl: 'https://www.congress.gov/votes', title: 'Congressional Vote' },
    'position-paper': { type: 'website', baseUrl: 'https://example.com/position', title: 'Position Paper' }
  };

  const sourceInfo = sourceTypeMap[type] || { type: 'website' as SourceType, baseUrl: 'https://example.com', title: 'Unknown Source' };
  
  return {
    url: `${sourceInfo.baseUrl}/${id}`,
    type: sourceInfo.type,
    title: `${sourceInfo.title} - ${id.replace(/-/g, ' ')}`,
    description: `Source reference from ${sourceInfo.title}`,
    last_accessed: "2024-03-15T19:15:00Z",
    is_fresh: false
  };
}

/**
 * Helper function to convert source strings array to Source objects array
 */
function createSources(sourceStrings: string[]): Source[] {
  return sourceStrings.map(createSource);
}

/**
 * Sample race data for fallback when API is unavailable
 * Enhanced with comprehensive realistic policy positions and donor data
 */
export const sampleRace: Race = {
  id: "sample-race-fallback",
  election_date: "2025-11-05T00:00:00Z",
  title: "Sample State U.S. Senate Race 2025",
  office: "U.S. Senate",
  jurisdiction: "Sample State",
  updated_utc: "2025-01-15T12:00:00Z",
  generator: ["gpt-4o", "claude-3.5", "grok-4"],
  candidates: [
    {
      name: "Senator Sarah Johnson",
      party: "Republican",
      incumbent: true,
      website: "https://www.sarahjohnsonforsenate.com",
      social_media: {
        twitter: "https://twitter.com/SenSarahJohnson",
        facebook: "https://facebook.com/SenatorSarahJohnson",
        instagram: "https://instagram.com/sarahjohnsonsenate"
      },
      summary: "Three-term incumbent Senator with a focus on fiscal conservatism, national security, and energy independence. Former state attorney general with 15 years of public service. Strong advocate for small businesses and rural communities. Sits on Armed Services and Energy committees.",
      issues: {
        Healthcare: {
          stance: "Supports market-based healthcare solutions, including health savings accounts and price transparency. Opposes government-run healthcare systems. Advocates for protecting pre-existing conditions coverage while reducing regulatory burden on providers. Supports telehealth expansion for rural areas.",
          confidence: "high",
          sources: createSources(["src:voting-record:aca-repeal-2023", "src:speech:healthcare-reform-summit-2024", "src:website:healthcare-policy"])
        },
        Economy: {
          stance: "Champions tax cuts for individuals and businesses, deregulation to spur growth, and reduced government spending. Strong supporter of domestic energy production. Opposes minimum wage increases, favors right-to-work laws. Advocates for balanced budget amendment.",
          confidence: "high",
          sources: createSources(["src:voting-record:tax-cuts-2024", "src:committee:budget-testimony", "src:op-ed:wall-street-journal-2024"])
        },
        "Climate/Energy": {
          stance: "Prioritizes energy independence through domestic oil, gas, and coal production. Supports nuclear energy expansion. Skeptical of climate regulations that harm economic growth. Opposes Green New Deal. Favors innovation-based climate solutions over mandates.",
          confidence: "high",
          sources: createSources(["src:committee:energy-hearing-2024", "src:statement:keystone-pipeline", "src:voting-record:epa-regulations"])
        },
        Immigration: {
          stance: "Strong border security advocate, supports completing border wall. Favors merit-based immigration system, opposes amnesty for undocumented immigrants. Supports e-verify mandate and increased deportations. Backs temporary worker programs for agriculture.",
          confidence: "high",
          sources: createSources(["src:floor-speech:border-security-2024", "src:bill:merit-immigration-act", "src:interview:fox-news-immigration"])
        },
        "Reproductive Rights": {
          stance: "Strongly pro-life, supports overturning Roe v. Wade. Favors federal 20-week abortion ban with exceptions for life of mother. Opposes federal funding for abortion. Supports adoption and crisis pregnancy centers. Backs parental notification laws.",
          confidence: "high",
          sources: createSources(["src:voting-record:planned-parenthood-defunding", "src:statement:dobbs-decision", "src:cosponsorship:life-at-conception-act"])
        },
        "Guns & Safety": {
          stance: "Strong Second Amendment advocate, opposes assault weapons bans and universal background checks. Supports national concealed carry reciprocity. Favors school security measures over gun restrictions. Opposes red flag laws as due process violations.",
          confidence: "high",
          sources: createSources(["src:nra-rating:a-plus-2024", "src:statement:uvalde-response", "src:voting-record:background-check-opposition"])
        },
        "Foreign Policy": {
          stance: "Supports peace through strength approach. Advocates for strong military, increased defense spending. Tough on China trade practices. Strong Israel supporter. Skeptical of international climate agreements. Favors NATO burden-sharing reforms.",
          confidence: "high",
          sources: createSources(["src:committee:armed-services-markup", "src:statement:ukraine-aid-conditions", "src:op-ed:china-threat-2024"])
        },
        "Social Justice": {
          stance: "Opposes affirmative action in college admissions and hiring. Supports law enforcement, opposes defunding police. Favors voter ID laws. Opposes federal LGBTQ+ anti-discrimination laws as states' rights issue. Supports religious freedom protections.",
          confidence: "medium",
          sources: createSources(["src:statement:supreme-court-affirmative-action", "src:vote:back-the-blue-act", "src:interview:religious-liberty"])
        },
        Education: {
          stance: "Supports school choice, including vouchers and charter schools. Opposes federal involvement in curriculum. Favors eliminating Department of Education. Supports student loan interest rate caps but opposes forgiveness programs. Backs trade school funding.",
          confidence: "high",
          sources: createSources(["src:bill:school-choice-expansion", "src:committee:education-hearing", "src:statement:student-loan-forgiveness"])
        },
        "Tech & AI": {
          stance: "Supports light-touch regulation of tech industry. Opposes antitrust breakup of major tech companies. Favors data privacy protections. Supports domestic semiconductor production. Cautious on AI regulation, prefers industry self-regulation initially.",
          confidence: "medium",
          sources: createSources(["src:hearing:big-tech-regulation", "src:statement:chips-act", "src:op-ed:ai-innovation-2024"])
        },
        "Election Reform": {
          stance: "Supports voter ID requirements, opposes automatic voter registration. Favors cleaning voter rolls. Opposes ranked choice voting. Supports paper ballot backup systems. Opposes federal takeover of election administration.",
          confidence: "high",
          sources: createSources(["src:bill:election-integrity-act", "src:statement:hr1-opposition", "src:interview:election-security"])
        }
      },
      top_donors: [
        {
          name: "Koch Industries PAC",
          amount: 25000.0,
          organization: "Energy/Manufacturing",
          source: createSource("src:fec:2024-q3-report")
        },
        {
          name: "National Rifle Association PAC",
          amount: 15000.0,
          organization: "Gun Rights",
          source: createSource("src:fec:2024-q2-report")
        },
        {
          name: "Chamber of Commerce PAC",
          amount: 20000.0,
          organization: "Business Advocacy",
          source: createSource("src:fec:2024-q3-report")
        },
        {
          name: "American Energy Alliance",
          amount: 12000.0,
          organization: "Energy Industry",
          source: createSource("src:fec:2024-q1-report")
        },
        {
          name: "Club for Growth PAC",
          amount: 18000.0,
          organization: "Conservative Economics",
          source: createSource("src:fec:2024-q2-report")
        }
      ]
    },
    {
      name: "Representative Maria Rodriguez",
      party: "Democratic",
      incumbent: false,
      website: "https://www.mariarodriguezforsenate.com",
      social_media: {
        twitter: "https://twitter.com/RepMariaRodriguez",
        facebook: "https://facebook.com/MariaRodriguezForSenate",
        instagram: "https://instagram.com/mariarodriguezsenate",
        tiktok: "https://tiktok.com/@mariarodriguezsenate"
      },
      summary: "Five-term House Representative and former public school teacher. First Latina to represent the state in Congress. Champion of working families, climate action, and healthcare access. Serves on Education and Healthcare committees. Former union organizer and civil rights attorney.",
      issues: {
        Healthcare: {
          stance: "Supports Medicare for All as ultimate goal, immediate public option expansion. Advocates for prescription drug price negotiation, dental and vision coverage. Wants to eliminate medical debt, expand community health centers. Strong supporter of reproductive healthcare access.",
          confidence: "high",
          sources: createSources(["src:bill:medicare-for-all-cosponsorship", "src:town-hall:healthcare-2024", "src:website:healthcare-detailed-plan"])
        },
        Economy: {
          stance: "Supports $15 federal minimum wage, strengthening unions and collective bargaining. Favors progressive taxation, closing corporate tax loopholes. Backs infrastructure investment, green jobs programs. Opposes right-to-work laws. Supports paid family leave.",
          confidence: "high",
          sources: createSources(["src:voting-record:raise-the-wage-act", "src:speech:labor-day-rally-2024", "src:bill:infrastructure-jobs-act"])
        },
        "Climate/Energy": {
          stance: "Strong supporter of Green New Deal, net-zero emissions by 2050. Advocates for massive renewable energy investment, ending fossil fuel subsidies. Supports rejoining Paris Agreement. Favors environmental justice measures for frontline communities.",
          confidence: "high",
          sources: createSources(["src:green-new-deal:original-cosponsor", "src:committee:climate-action-plan", "src:rally:climate-strike-2024"])
        },
        Immigration: {
          stance: "Supports comprehensive immigration reform with pathway to citizenship for undocumented immigrants. Opposes family separation, border wall. Favors increasing refugee admissions, DREAM Act passage. Supports ending Title 42, reforming ICE.",
          confidence: "high",
          sources: createSources(["src:bill:comprehensive-immigration-reform", "src:border-visit:2024", "src:statement:dreamer-protection"])
        },
        "Reproductive Rights": {
          stance: "Strongly pro-choice, supports codifying Roe v. Wade into federal law. Opposes all abortion restrictions, supports federal funding for abortion. Advocates for expanding access to contraception, comprehensive sex education. Supports fertility treatment coverage.",
          confidence: "high",
          sources: createSources(["src:voting-record:womens-health-protection-act", "src:statement:dobbs-response", "src:planned-parenthood:endorsement"])
        },
        "Guns & Safety": {
          stance: "Supports universal background checks, assault weapons ban, high-capacity magazine restrictions. Advocates for red flag laws, mandatory safe storage requirements. Supports funding for gun violence research, community intervention programs.",
          confidence: "high",
          sources: createSources(["src:bill:universal-background-checks", "src:press-conference:uvalde-response", "src:brady-campaign:endorsement"])
        },
        "Foreign Policy": {
          stance: "Supports multilateral diplomacy, strengthening NATO alliances. Advocates for human rights-centered foreign policy. Opposes unnecessary military interventions. Supports foreign aid, addressing global climate change. Favors nuclear disarmament efforts.",
          confidence: "medium",
          sources: createSources(["src:committee:foreign-affairs-statement", "src:op-ed:diplomacy-first-2024", "src:vote:war-powers-resolution"])
        },
        "Social Justice": {
          stance: "Strong civil rights advocate, supports Equality Act for LGBTQ+ protections. Backs criminal justice reform, ending private prisons. Supports voting rights expansion, opposes voter suppression. Advocates for police accountability, community policing reforms.",
          confidence: "high",
          sources: createSources(["src:bill:equality-act-cosponsor", "src:march:voting-rights-2024", "src:statement:george-floyd-justice-act"])
        },
        Education: {
          stance: "Supports free community college, student loan forgiveness programs. Advocates for universal pre-K, increased teacher pay. Opposes school voucher programs. Supports Title I funding increases, special education resources. Backs trade school investments.",
          confidence: "high",
          sources: createSources(["src:bill:college-for-all-act", "src:nea-endorsement:2024", "src:committee:education-budget-testimony"])
        },
        "Tech & AI": {
          stance: "Supports tech industry regulation, antitrust enforcement against big tech. Advocates for data privacy protections, net neutrality. Favors AI ethics standards, algorithmic bias prevention. Supports digital divide initiatives, broadband as utility.",
          confidence: "medium",
          sources: createSources(["src:hearing:big-tech-accountability", "src:bill:data-privacy-act", "src:op-ed:ai-regulation-framework"])
        },
        "Election Reform": {
          stance: "Supports automatic voter registration, making Election Day a holiday. Advocates for ending gerrymandering, campaign finance reform. Opposes voter ID requirements as suppression. Supports restoring Voting Rights Act, D.C. statehood.",
          confidence: "high",
          sources: createSources(["src:bill:for-the-people-act", "src:statement:voting-rights-advancement", "src:rally:democracy-reform-2024"])
        }
      },
      top_donors: [
        {
          name: "EMILY's List",
          amount: 28000.0,
          organization: "Women's Political Advocacy",
          source: createSource("src:fec:2024-q3-report")
        },
        {
          name: "AFL-CIO PAC",
          amount: 22000.0,
          organization: "Labor Union",
          source: createSource("src:fec:2024-q2-report")
        },
        {
          name: "League of Conservation Voters",
          amount: 18000.0,
          organization: "Environmental Advocacy",
          source: createSource("src:fec:2024-q3-report")
        },
        {
          name: "SEIU PAC",
          amount: 20000.0,
          organization: "Service Workers Union",
          source: createSource("src:fec:2024-q1-report")
        },
        {
          name: "Planned Parenthood Action Fund",
          amount: 15000.0,
          organization: "Reproductive Rights",
          source: createSource("src:fec:2024-q2-report")
        },
        {
          name: "Human Rights Campaign PAC",
          amount: 12000.0,
          organization: "LGBTQ+ Rights",
          source: createSource("src:fec:2024-q3-report")
        }
      ]
    },
    {
      name: "Michael Thompson",
      party: "Independent",
      incumbent: false,
      website: "https://www.michaelthompsonindependent.com",
      social_media: {
        twitter: "https://twitter.com/MikeThompsonInd",
        facebook: "https://facebook.com/ThompsonIndependent"
      },
      summary: "Former military officer and small business owner running as an independent. Purple Heart veteran with two tours in Afghanistan. Advocates for pragmatic, bipartisan solutions. Owns a renewable energy consulting firm. Focuses on fiscal responsibility and governmental reform.",
      issues: {
        Healthcare: {
          stance: "Supports bipartisan healthcare reform combining market solutions with public options. Advocates for price transparency, interstate insurance sales, and protecting pre-existing conditions. Favors gradual Medicare expansion for those 55+.",
          confidence: "medium",
          sources: createSources(["src:policy-paper:healthcare-reform", "src:interview:local-news-healthcare", "src:website:third-way-healthcare"])
        },
        Economy: {
          stance: "Fiscally conservative, socially moderate approach. Supports simplified tax code, reducing federal deficit through spending reforms and targeted revenue increases. Backs infrastructure investment funded through public-private partnerships.",
          confidence: "high",
          sources: createSources(["src:position-paper:fiscal-responsibility", "src:debate:economic-policy", "src:endorsement:taxpayers-union"])
        },
        "Climate/Energy": {
          stance: "Supports all-of-the-above energy strategy including renewables, nuclear, and cleaner fossil fuels. Advocates for carbon pricing, innovation incentives. Opposes overly rapid transitions that harm workers. Supports climate adaptation measures.",
          confidence: "high",
          sources: createSources(["src:business-background:renewable-energy", "src:op-ed:practical-climate-action", "src:interview:energy-policy"])
        },
        Immigration: {
          stance: "Supports comprehensive immigration reform with border security improvements and earned pathway to citizenship. Advocates for streamlined legal immigration, guest worker programs. Opposes family separation but supports orderly deportation processes.",
          confidence: "medium",
          sources: createSources(["src:forum:immigration-reform", "src:statement:border-visit", "src:website:immigration-plan"])
        },
        "Reproductive Rights": {
          stance: "Personally pro-life but believes government should have limited role in personal medical decisions. Supports exceptions for rape, incest, and life of mother. Favors state-level decision making on abortion policy.",
          confidence: "low",
          sources: createSources(["src:interview:personal-views", "src:debate:reproductive-rights", "src:statement:roe-decision"])
        },
        "Guns & Safety": {
          stance: "Second Amendment supporter who also backs common-sense safety measures. Supports improved background checks, veteran mental health programs. Opposes assault weapon bans but supports safe storage requirements.",
          confidence: "medium",
          sources: createSources(["src:military-background:gun-safety", "src:forum:second-amendment", "src:interview:gun-violence-prevention"])
        },
        "Foreign Policy": {
          stance: "Strong national defense with careful consideration of military interventions. Supports NATO, strategic competition with China. Advocates for veteran affairs reform. Favors diplomacy-first approach backed by military strength.",
          confidence: "high",
          sources: createSources(["src:military-service:afghanistan", "src:op-ed:foreign-policy-realism", "src:veterans-forum:2024"])
        },
        "Social Justice": {
          stance: "Supports equal treatment under law regardless of race, gender, or sexual orientation. Backs criminal justice reform, police training improvements. Believes in addressing racial inequities through education and economic opportunity.",
          confidence: "medium",
          sources: createSources(["src:forum:civil-rights", "src:statement:police-reform", "src:interview:social-issues"])
        },
        Education: {
          stance: "Supports school choice options including charter schools while maintaining strong public education funding. Advocates for trade school expansion, student loan interest rate reforms. Opposes federal curriculum mandates.",
          confidence: "medium",
          sources: createSources(["src:education-forum:2024", "src:website:education-policy", "src:statement:vocational-training"])
        },
        "Tech & AI": {
          stance: "Supports balanced approach to tech regulation, promoting innovation while protecting privacy. Advocates for bipartisan AI oversight commission. Favors antitrust enforcement against anti-competitive practices but opposes punitive breakups.",
          confidence: "low",
          sources: createSources(["src:business-background:technology", "src:interview:tech-regulation", "src:position-paper:innovation-policy"])
        },
        "Election Reform": {
          stance: "Supports non-partisan redistricting commissions, campaign finance transparency. Backs voter ID with free ID provision. Opposes gerrymandering by both parties. Advocates for ranked choice voting in federal elections.",
          confidence: "medium",
          sources: createSources(["src:website:government-reform", "src:interview:election-integrity", "src:endorsement:good-government-groups"])
        }
      },
      top_donors: [
        {
          name: "Veterans for Thompson",
          amount: 8500.0,
          organization: "Veteran Advocacy",
          source: createSource("src:fec:2024-q3-report")
        },
        {
          name: "Small Business Coalition",
          amount: 6200.0,
          organization: "Business Advocacy",
          source: createSource("src:fec:2024-q2-report")
        },
        {
          name: "Clean Energy PAC",
          amount: 7800.0,
          organization: "Renewable Energy",
          source: createSource("src:fec:2024-q3-report")
        },
        {
          name: "Good Government Fund",
          amount: 5000.0,
          organization: "Government Reform",
          source: createSource("src:fec:2024-q1-report")
        }
      ]
    }
  ]
};
/**
 * Map of sample races by slug for fallback data
 */
export const sampleRaces: Record<string, Race> = {
  "sample-race": sampleRace,
  "mo-senate-2024": {
    ...sampleRace,
    id: "mo-senate-2024",
    title: "Missouri U.S. Senate Race 2024",
    jurisdiction: "Missouri"
  },
  "ca-senate-2024": {
    ...sampleRace,
    id: "ca-senate-2024",
    title: "California U.S. Senate Race 2024",
    jurisdiction: "California"
  },
  "ny-house-03-2024": {
    ...sampleRace,
    id: "ny-house-03-2024",
    title: "New York House District 3 Race 2024",
    office: "U.S. House",
    jurisdiction: "New York District 3"
  },
  "tx-governor-2024": {
    ...sampleRace,
    id: "tx-governor-2024",
    title: "Texas Governor Race 2024",
    office: "Governor",
    jurisdiction: "Texas"
  }
};
