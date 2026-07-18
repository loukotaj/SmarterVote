<script lang="ts">
  import { browser } from "$app/environment";
  import { goto } from "$app/navigation";
  import { page } from "$app/stores";
  import TabButton from "$lib/components/TabButton.svelte";
  import USMap from "$lib/components/USMap.svelte";
  import type {
    ChamberForecasts,
    ForecastRating,
    RaceSummary,
  } from "$lib/types";
  import {
    aggregateForecasts,
    formatNet,
    formatRating,
    normalizeForecastParty,
    getRaceState,
    isRaceInForecastTab,
    parseForecastTab,
    type ForecastTab,
    INCUMBENT_FALLBACKS,
    groupSeatDistribution,
  } from "$lib/utils/forecast";
  import { GOVERNOR_HOLDOVERS, SENATE_HOLDOVERS } from "$lib/utils/holdovers";

  const tabs: { id: ForecastTab; label: string }[] = [
    { id: "house", label: "House" },
    { id: "senate", label: "Senate" },
    { id: "governors", label: "Governors" },
  ];

  const ratingOrder: ForecastRating[] = [
    "safe_d",
    "likely_d",
    "lean_d",
    "tilt_d",
    "tossup",
    "tilt_r",
    "lean_r",
    "likely_r",
    "safe_r",
  ];

  let activeTab: ForecastTab = "house";
  let selectedState: string | null = null;
  let showHoldovers = false;

  let filterRating: string = "all";
  let filterParty: string = "all";
  let sortBy: string = "control_relevance";
  let expandedRaceIds = new Set<string>();
  let expandedRaceTab: ForecastTab = activeTab;

  let activeChartType: "buckets" | "histogram" | "curve" = "buckets";
  let visibleRaceCount = 9;

  $: races = ($page.data.races as RaceSummary[] | undefined) ?? [];
  $: activeTab = browser
    ? parseForecastTab($page.url.searchParams.get("tab"))
    : "house";
  $: selectedState = browser
    ? $page.url.searchParams.get("state") || null
    : null;
  $: aggregate = aggregateForecasts(races, activeTab);

  $: chamberForecasts = $page.data.chamberForecasts as
    | ChamberForecasts
    | undefined;
  $: chamberSummary = chamberForecasts?.chambers?.[activeTab];
  $: chamberNarrative =
    chamberSummary?.narrative || chamberForecasts?.[activeTab] || "";

  $: {
    // Reset visible race count on tab or filter change
    (activeTab, selectedState, filterRating, filterParty);
    visibleRaceCount = 9;
  }

  $: if (activeTab !== expandedRaceTab) {
    expandedRaceIds.clear();
    expandedRaceIds = expandedRaceIds;
    expandedRaceTab = activeTab;
  }

  $: seatBuckets = groupSeatDistribution(
    chamberSummary?.seat_distribution ?? {},
    activeTab,
  );
  $: sortedOutcomes = Object.entries(chamberSummary?.seat_distribution ?? {})
    .map(([key, prob]) => {
      const matchD = key.match(/(\d+)D/);
      const matchR = key.match(/(\d+)R/);
      const d = matchD ? parseInt(matchD[1], 10) : 50;
      const r = matchR ? parseInt(matchR[1], 10) : 50;
      return { key, probability: prob, dSeats: d, rSeats: r };
    })
    .sort((a, b) => b.dSeats - a.dSeats);
  $: maxProbability = Math.max(
    ...sortedOutcomes.map((o) => o.probability),
    0.01,
  );
  $: svgData = (() => {
    if (sortedOutcomes.length === 0)
      return {
        fillPath: "",
        strokePath: "",
        points: [],
        tieX: 150,
        minD: 45,
        maxD: 55,
      };
    const minD = Math.min(...sortedOutcomes.map((o) => o.dSeats));
    const maxD = Math.max(...sortedOutcomes.map((o) => o.dSeats));
    const span = maxD - minD || 1;
    const maxP = Math.max(...sortedOutcomes.map((o) => o.probability), 0.01);
    // Use the majority threshold for the tie-break line on the curve
    const tieThreshold = chamberSummary?.threshold ?? 51;

    const points = sortedOutcomes.map((o) => {
      const pctX = (o.dSeats - minD) / span;
      const pctY = o.probability / maxP;
      return {
        x: 15 + pctX * 270, // 300px wide
        y: 85 - pctY * 75, // 100px high
        dSeats: o.dSeats,
        rSeats: o.rSeats,
        prob: o.probability,
      };
    });

    let fillPath = "";
    let strokePath = "";
    if (points.length > 0) {
      fillPath = `M ${points[0].x} 85 `;
      strokePath = `M ${points[0].x} ${points[0].y} `;
      for (const pt of points) {
        fillPath += `L ${pt.x} ${pt.y} `;
        strokePath += `L ${pt.x} ${pt.y} `;
      }
      fillPath += `L ${points[points.length - 1].x} 85 Z`;
    }

    let tieX = 150;
    if (tieThreshold >= minD && tieThreshold <= maxD) {
      tieX = 15 + ((tieThreshold - minD) / span) * 270;
    } else if (tieThreshold < minD) {
      tieX = 15;
    } else {
      tieX = 285;
    }

    return { fillPath, strokePath, points, tieX, minD, maxD };
  })();

  $: projectedSeats = chamberSummary?.projected_seats ?? aggregate.projected;
  $: expectedSeats = chamberSummary?.expected_seats;
  $: outcomeProbabilities = chamberSummary?.outcome_probabilities;
  $: totalSeats = chamberSummary?.total_seats ?? aggregate.totalExpected;
  $: threshold = chamberSummary?.threshold ?? aggregate.threshold;
  $: controlParty =
    chamberSummary?.control_party ??
    (activeTab === "senate" &&
    (aggregate.projected.Democratic ?? 0) === 50 &&
    (aggregate.projected.Republican ?? 0) === 50
      ? "Republican"
      : (aggregate.projected.Democratic ?? 0) >= aggregate.threshold
        ? "Democratic"
        : (aggregate.projected.Republican ?? 0) >= aggregate.threshold
          ? "Republican"
          : "Other");

  // Filter active states for the map click handler
  $: activeStates = new Set(
    races
      .filter((r) => isRaceInForecastTab(r, activeTab))
      .map(getRaceState)
      .filter(Boolean) as string[],
  );
  $: stateRaceCounts = races
    .filter((race) => isRaceInForecastTab(race, activeTab))
    .reduce<Record<string, number>>((counts, race) => {
      const state = getRaceState(race);
      if (state) counts[state] = (counts[state] ?? 0) + 1;
      return counts;
    }, {});

  // Dynamic colors and tooltips for the map
  type StateTooltip = {
    title: string;
    subtitle?: string;
    badge?: string;
    badgeClass?: string;
    details?: string[];
  };

  let stateColors: Record<string, string> = {};
  let stateTooltips: Record<string, StateTooltip> = {};

  $: {
    const colors: Record<string, string> = {};
    const tooltips: Record<string, StateTooltip> = {};

    const activeRaces = races.filter((r) => isRaceInForecastTab(r, activeTab));

    if (activeTab === "governors") {
      // Process holdovers
      for (const [state, party] of Object.entries(GOVERNOR_HOLDOVERS)) {
        colors[state] =
          party === "Democratic"
            ? "var(--color-holdover-d)"
            : "var(--color-holdover-r)";
        tooltips[state] = {
          title: state,
          subtitle: "No election in 2026",
          badge: `${
            party === "Democratic" ? "Democratic" : "Republican"
          } Holdover`,
          badgeClass:
            party === "Democratic"
              ? "!bg-blue-600/90 !text-white"
              : "!bg-red-600/90 !text-white",
          details: ["Incumbent Governor holds seat"],
        };
      }

      // Process active races
      for (const r of activeRaces) {
        const state = getRaceState(r);
        if (!state) continue;

        if (r.forecast) {
          const rating = r.forecast.rating;
          colors[state] = colorForRating(rating);
          const winProbText = r.forecast.win_probability
            ? ` (${Math.round(r.forecast.win_probability * 100)}% prob.)`
            : "";
          const marginText =
            r.forecast.margin_estimate !== undefined &&
            r.forecast.margin_estimate !== null
              ? ` +${r.forecast.margin_estimate.toFixed(1)} pts`
              : "";

          tooltips[state] = {
            title: state,
            subtitle: "2026 Governor Race",
            badge: formatRating(rating),
            badgeClass: rating.endsWith("_d")
              ? "!bg-blue-600 !text-white"
              : rating.endsWith("_r")
                ? "!bg-red-600 !text-white"
                : "!bg-slate-500 !text-white",
            details: [
              `Projected: ${
                r.forecast.predicted_winner_name ||
                r.forecast.predicted_winner_party
              }${winProbText}`,
              `Est. Margin: ${marginText || "n/a"}`,
              r.forecast.rationale.length > 90
                ? r.forecast.rationale.slice(0, 90) + "..."
                : r.forecast.rationale,
            ],
          };
        } else {
          colors[state] = "var(--color-tossup)";
          tooltips[state] = {
            title: state,
            subtitle: "2026 Governor Race",
            badge: "Unforecasted",
            badgeClass: "!bg-slate-500 !text-white",
            details: ["No published model forecasts yet"],
          };
        }
      }
    } else if (activeTab === "senate") {
      // Process holdovers
      for (const [state, parties] of Object.entries(SENATE_HOLDOVERS)) {
        const isActive = activeStates.has(state);
        const holdoverSeats = isActive ? parties.slice(0, 1) : parties;

        if (!isActive) {
          if (holdoverSeats.length === 2) {
            const p1 = holdoverSeats[0];
            const p2 = holdoverSeats[1];
            if (p1 === p2) {
              colors[state] =
                p1 === "Democratic"
                  ? "var(--color-holdover-d)"
                  : "var(--color-holdover-r)";
            } else {
              colors[state] = "var(--color-tossup)";
            }
          } else {
            colors[state] =
              holdoverSeats[0] === "Democratic"
                ? "var(--color-holdover-d)"
                : "var(--color-holdover-r)";
          }

          const seatStrings = holdoverSeats.map((p) =>
            p === "Democratic" ? "Democrat" : "Republican",
          );
          tooltips[state] = {
            title: state,
            subtitle: "No election in 2026",
            badge: `${holdoverSeats.length} Holdover Seat${
              holdoverSeats.length > 1 ? "s" : ""
            }`,
            badgeClass: "!bg-slate-500 !text-white",
            details: seatStrings.map((s, idx) => `Seat ${idx + 1}: ${s}`),
          };
        }
      }

      // Process active races
      for (const r of activeRaces) {
        const state = getRaceState(r);
        if (!state) continue;

        const parties = SENATE_HOLDOVERS[state] || [];
        const holdoverSeat = parties.length > 0 ? parties[0] : null;

        if (r.forecast) {
          const rating = r.forecast.rating;
          colors[state] = colorForRating(rating);
          const winProbText = r.forecast.win_probability
            ? ` (${Math.round(r.forecast.win_probability * 100)}% prob.)`
            : "";
          const marginText =
            r.forecast.margin_estimate !== undefined &&
            r.forecast.margin_estimate !== null
              ? ` +${r.forecast.margin_estimate.toFixed(1)} pts`
              : "";

          const details = [
            `Projected: ${
              r.forecast.predicted_winner_name ||
              r.forecast.predicted_winner_party
            }${winProbText}`,
            `Est. Margin: ${marginText || "n/a"}`,
          ];
          if (holdoverSeat) {
            details.push(
              `Holdover Seat: ${
                holdoverSeat === "Democratic" ? "Democrat" : "Republican"
              }`,
            );
          }
          details.push(
            r.forecast.rationale.length > 90
              ? r.forecast.rationale.slice(0, 90) + "..."
              : r.forecast.rationale,
          );

          tooltips[state] = {
            title: state,
            subtitle: "2026 Senate Election",
            badge: formatRating(rating),
            badgeClass: rating.endsWith("_d")
              ? "!bg-blue-600 !text-white"
              : rating.endsWith("_r")
                ? "!bg-red-600 !text-white"
                : "!bg-slate-500 !text-white",
            details,
          };
        } else {
          colors[state] = "var(--color-tossup)";
          const details = ["No published model forecasts yet"];
          if (holdoverSeat) {
            details.push(
              `Holdover Seat: ${
                holdoverSeat === "Democratic" ? "Democrat" : "Republican"
              }`,
            );
          }
          tooltips[state] = {
            title: state,
            subtitle: "2026 Senate Election",
            badge: "Unforecasted",
            badgeClass: "!bg-slate-500 !text-white",
            details,
          };
        }
      }
    } else {
      // House
      const states = new Set(
        activeRaces.map(getRaceState).filter(Boolean) as string[],
      );
      for (const state of states) {
        if (!state) continue;

        const stateRaces = activeRaces.filter((h) => getRaceState(h) === state);
        const count = stateRaces.length;
        const summary = summarizeStateForecast(stateRaces);

        colors[state] = summary.primary?.forecast
          ? colorForRating(summary.primary.forecast.rating)
          : "var(--color-tossup)";

        tooltips[state] = {
          title: state,
          subtitle: `${count} House race${count > 1 ? "s" : ""} in scope`,
          badge: summary.primary?.forecast
            ? `${formatRating(summary.primary.forecast.rating)} bellwether`
            : `${summary.forecastedCount}/${count} Forecasted`,
          badgeClass: summary.primary?.forecast?.rating.endsWith("_d")
            ? "!bg-blue-600 !text-white"
            : summary.primary?.forecast?.rating.endsWith("_r")
              ? "!bg-red-600 !text-white"
              : "!bg-slate-500 !text-white",
          details:
            summary.details.length > 0
              ? [
                  ...summary.details,
                  `${summary.competitiveCount} competitive forecasted seat${
                    summary.competitiveCount === 1 ? "" : "s"
                  }`,
                  "Click state to filter races below",
                ]
              : [
                  "No published model forecasts yet",
                  "Click state to filter races below",
                ],
        };
      }
    }

    stateColors = colors;
    stateTooltips = tooltips;
  }

  function handleStateClick(event: CustomEvent<string>) {
    const stateName = event.detail;
    setUrlState(activeTab, selectedState === stateName ? null : stateName);
  }

  function setActiveTab(tab: ForecastTab) {
    setUrlState(tab, null);
  }

  function setUrlState(tab: ForecastTab, state: string | null) {
    if (!browser) return;
    const params = new URLSearchParams($page.url.searchParams);
    if (tab === "house") {
      params.delete("tab");
    } else {
      params.set("tab", tab);
    }
    if (state) {
      params.set("state", state);
    } else {
      params.delete("state");
    }
    const query = params.toString();
    goto(`/forecast${query ? `?${query}` : ""}`, {
      replaceState: true,
      keepFocus: true,
      noScroll: true,
    });
  }

  function toggleExpand(raceId: string) {
    if (expandedRaceIds.has(raceId)) {
      expandedRaceIds.delete(raceId);
    } else {
      expandedRaceIds.add(raceId);
    }
    expandedRaceIds = expandedRaceIds;
  }

  function getControlRelevanceScore(race: RaceSummary): number {
    const title = race.title || "";
    const id = race.id || "";
    const isKey = chamberSummary?.competitive_races?.some(
      (t) => t === title || title.includes(t) || id.includes(t),
    );

    let ratingPriority = 4;
    if (race.forecast) {
      const r = race.forecast.rating.toLowerCase();
      if (r.includes("tossup") || r.includes("toss-up")) {
        ratingPriority = 0;
      } else if (r.includes("tilt")) {
        ratingPriority = 1;
      } else if (r.includes("lean")) {
        ratingPriority = 2;
      } else if (r.includes("likely")) {
        ratingPriority = 3;
      } else if (r.includes("safe")) {
        ratingPriority = 4;
      }
    }

    const winProb = race.forecast?.win_probability ?? 0.5;
    const closeness = Math.abs(winProb - 0.5);

    const keyWeight = isKey ? 0 : 1000;
    const ratingWeight = ratingPriority * 100;
    const closenessWeight = closeness * 10;

    return keyWeight + ratingWeight + closenessWeight;
  }

  function getHostname(urlString: string): string {
    try {
      return new URL(urlString).hostname.replace("www.", "");
    } catch (e) {
      return "Source Link";
    }
  }

  function isExternalUrl(urlString?: string | null): boolean {
    if (!urlString) return false;
    try {
      const url = new URL(urlString);
      return url.protocol === "http:" || url.protocol === "https:";
    } catch (e) {
      return false;
    }
  }

  $: filteredRaces = aggregate.races
    .filter((race) => {
      if (selectedState && getRaceState(race) !== selectedState) return false;

      if (filterRating !== "all") {
        const rating = race.forecast.rating.toLowerCase();
        if (filterRating === "tossup" && !rating.includes("tossup"))
          return false;
        if (filterRating === "tilt" && !rating.startsWith("tilt_"))
          return false;
        if (filterRating === "lean" && !rating.startsWith("lean_"))
          return false;
        if (
          filterRating === "likely_safe" &&
          !rating.startsWith("likely_") &&
          !rating.startsWith("safe_")
        )
          return false;
      }
      if (filterParty !== "all") {
        const party = normalizeForecastParty(
          race.forecast.predicted_winner_party,
          race.forecast.party_probabilities,
          race.candidates,
        );
        if (filterParty !== party) return false;
      }

      return true;
    })
    .sort((a, b) => {
      if (sortBy === "state") {
        const stateA = getRaceState(a) || "";
        const stateB = getRaceState(b) || "";
        return stateA.localeCompare(stateB);
      }
      if (sortBy === "rating") {
        const indexA = ratingOrder.indexOf(a.forecast.rating);
        const indexB = ratingOrder.indexOf(b.forecast.rating);
        return indexA - indexB;
      }
      if (sortBy === "probability") {
        const probA = a.forecast.win_probability ?? 0;
        const probB = b.forecast.win_probability ?? 0;
        return probB - probA;
      }
      if (sortBy === "margin") {
        const marginA = Math.abs(a.forecast.margin_estimate ?? 0);
        const marginB = Math.abs(b.forecast.margin_estimate ?? 0);
        return marginB - marginA;
      }
      if (sortBy === "dem_pickup") {
        const demProbA = a.forecast.party_probabilities?.Democratic ?? 0;
        const demProbB = b.forecast.party_probabilities?.Democratic ?? 0;
        return demProbB - demProbA;
      }
      if (sortBy === "gop_pickup") {
        const gopProbA = a.forecast.party_probabilities?.Republican ?? 0;
        const gopProbB = b.forecast.party_probabilities?.Republican ?? 0;
        return gopProbB - gopProbA;
      }
      if (sortBy === "competitiveness") {
        const diffA = Math.abs((a.forecast.win_probability ?? 0.5) - 0.5);
        const diffB = Math.abs((b.forecast.win_probability ?? 0.5) - 0.5);
        return diffA - diffB;
      }
      return getControlRelevanceScore(a) - getControlRelevanceScore(b);
    });

  $: sortedRaces = filteredRaces;

  $: keyRacesList = races.filter((r) => {
    if (!isRaceInForecastTab(r, activeTab)) return false;
    const title = r.title || "";
    const id = r.id || "";
    return chamberSummary?.competitive_races?.some(
      (t) => t === title || title.includes(t) || id.includes(t),
    );
  });

  $: filteredMissingRaces = selectedState
    ? aggregate.missingForecasts.filter(
        (r) => getRaceState(r) === selectedState,
      )
    : aggregate.missingForecasts;

  function partyClass(party: string): string {
    if (party === "Democratic") return "text-blue-600 dark:text-blue-400";
    if (party === "Republican") return "text-red-600 dark:text-red-400";
    return "text-content-muted";
  }

  function ratingClass(rating: ForecastRating): string {
    if (rating.endsWith("_d"))
      return "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/40 dark:text-blue-200 dark:border-blue-800/60";
    if (rating.endsWith("_r"))
      return "bg-red-50 text-red-700 border-red-200 dark:bg-red-950/40 dark:text-red-200 dark:border-red-800/60";
    return "bg-slate-50 text-slate-700 border-slate-200 dark:bg-slate-800/40 dark:text-slate-200 dark:border-slate-700/60";
  }

  function colorForRating(rating: ForecastRating): string {
    return `var(--color-${rating.replace("_", "-")})`;
  }

  function ratingCompetitiveness(rating: ForecastRating): number {
    if (rating === "tossup") return 0;
    if (rating.startsWith("tilt_")) return 1;
    if (rating.startsWith("lean_")) return 2;
    if (rating.startsWith("likely_")) return 3;
    if (rating.startsWith("safe_")) return 4;
    return 5;
  }

  function summarizeStateForecast(stateRaces: RaceSummary[]) {
    const forecasted = stateRaces.filter((race) => race.forecast);
    const sorted = [...forecasted].sort((a, b) => {
      const aForecast = a.forecast!;
      const bForecast = b.forecast!;
      const priority =
        ratingCompetitiveness(aForecast.rating) -
        ratingCompetitiveness(bForecast.rating);
      if (priority !== 0) return priority;
      return (
        Math.abs((aForecast.win_probability ?? 0.5) - 0.5) -
        Math.abs((bForecast.win_probability ?? 0.5) - 0.5)
      );
    });

    return {
      primary: sorted[0],
      forecastedCount: forecasted.length,
      competitiveCount: forecasted.filter(
        (race) => ratingCompetitiveness(race.forecast!.rating) <= 2,
      ).length,
      details: sorted.slice(0, 3).map((race) => {
        const forecast = race.forecast!;
        const party = normalizeForecastParty(
          forecast.predicted_winner_party,
          forecast.party_probabilities,
          race.candidates,
        );
        const winProb = forecast.win_probability
          ? `, ${Math.round(forecast.win_probability * 100)}% ${
              party === "Democratic"
                ? "D"
                : party === "Republican"
                  ? "R"
                  : party
            }`
          : "";
        return `${race.title ?? race.id}: ${formatRating(
          forecast.rating,
        )}${winProb}`;
      }),
    };
  }

  function probability(value?: number): string {
    if (value === undefined || value === null) return "n/a";
    if (value >= 1) return ">99%";
    if (value <= 0) return "<1%";
    return `${Math.round(value * 100)}%`;
  }

  function probabilityOneDecimal(value?: number | null): string {
    if (value === undefined || value === null) return "n/a";
    return `${(value * 100).toFixed(1)}%`;
  }

  function marketSignalTarget(signal: {
    matched_to: string;
    matched_party?: string;
  }): string {
    if (signal.matched_party && signal.matched_party !== signal.matched_to) {
      return `${signal.matched_to} (${signal.matched_party})`;
    }
    return signal.matched_to;
  }

  function marketSpread(signal: {
    yes_bid?: number | null;
    yes_ask?: number | null;
  }): string | null {
    if (
      typeof signal.yes_bid !== "number" ||
      typeof signal.yes_ask !== "number"
    ) {
      return null;
    }
    return `${probabilityOneDecimal(
      signal.yes_bid,
    )} bid / ${probabilityOneDecimal(signal.yes_ask)} ask`;
  }

  function marketAsOf(value?: string | null): string {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  }

  function oneDecimal(value?: number): string {
    if (value === undefined || value === null) return "n/a";
    return value.toFixed(1);
  }

  function clearStateFilter() {
    setUrlState(activeTab, null);
  }

  function raceHref(id: string): string {
    return `/races/${id}`;
  }

  const controlParties: ("Democratic" | "Republican" | "Other")[] = [
    "Democratic",
    "Republican",
    "Other",
  ];

  // Most likely outcome from seat distribution
  $: mostLikelyOutcome = (() => {
    const dist = chamberSummary?.seat_distribution ?? {};
    let best = { key: "", probability: 0 };
    for (const [key, prob] of Object.entries(dist)) {
      if (prob > best.probability) best = { key, probability: prob };
    }
    return best;
  })();

  // Scrollable key races strip
  let keyRacesContainer: HTMLDivElement;
  function scrollKeyRaces(dir: number) {
    keyRacesContainer?.scrollBy({ left: dir * 320, behavior: "smooth" });
  }
</script>

<svelte:head>
  <title>2026 Election Forecasts — Smarter.vote</title>
  <meta
    name="description"
    content="AI-powered forecasts and interactive maps for 2026 House, Senate, and Governor races. See win probabilities, polling data, and prediction market signals."
  />
  <link rel="canonical" href="https://smarter.vote/forecast/" />
  <meta property="og:type" content="article" />
  <meta property="og:url" content="https://smarter.vote/forecast/" />
  <meta property="og:title" content="2026 Election Forecasts — Smarter.vote" />
  <meta
    property="og:description"
    content="AI-powered forecasts and interactive maps for 2026 House, Senate, and Governor races. See win probabilities, polling data, and prediction market signals."
  />
  <meta property="og:image" content="https://smarter.vote/og-image.png" />
  <meta property="twitter:card" content="summary_large_image" />
  <meta property="twitter:url" content="https://smarter.vote/forecast/" />
  <meta
    property="twitter:title"
    content="2026 Election Forecasts — Smarter.vote"
  />
  <meta
    property="twitter:description"
    content="AI-powered forecasts and interactive maps for 2026 House, Senate, and Governor races. See win probabilities, polling data, and prediction market signals."
  />
  <meta property="twitter:image" content="https://smarter.vote/og-image.png" />
</svelte:head>

<div class="forecast-page max-w-7xl mx-auto px-4 py-8 sm:py-10 space-y-8">
  <header>
    <div
      class="flex flex-col md:flex-row md:items-center md:justify-between gap-4"
    >
      <div>
        <h1
          class="text-4xl font-extrabold text-content tracking-tight bg-gradient-to-r from-blue-600 to-red-600 bg-clip-text text-transparent dark:from-blue-400 dark:to-red-400"
        >
          2026 Election Forecast
        </h1>
        <p class="mt-2 text-base text-content-muted max-w-3xl">
          Nonpartisan model projections, interactive maps, and structured
          analysis for the 2026 House, Senate, and Governor races.
        </p>
      </div>
      <div
        class="text-xs text-content-subtle border border-stroke/80 bg-surface-alt/40 backdrop-blur-md px-3 py-2 rounded-xl flex items-center gap-1.5 self-start md:self-auto"
      >
        <span class="relative flex h-2 w-2">
          <span
            class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"
          ></span>
          <span class="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"
          ></span>
        </span>
        Model status: Live
      </div>
    </div>
  </header>

  {#if (!races || races.length === 0) && (!chamberForecasts || !chamberForecasts.chambers)}
    <div
      class="max-w-2xl mx-auto my-16 p-8 bg-surface-alt border border-stroke/80 rounded-2xl text-center space-y-4"
    >
      <div
        class="w-12 h-12 bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 rounded-full flex items-center justify-center mx-auto animate-pulse"
      >
        <svg
          class="w-6 h-6"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          viewBox="0 0 24 24"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
          />
        </svg>
      </div>
      <h2 class="text-lg font-black text-content text-center">
        Forecast Data Unavailable
      </h2>
      <p
        class="text-xs text-content-muted leading-relaxed font-semibold max-w-sm mx-auto text-center"
      >
        We are currently updating our election models. Please check back shortly
        for the latest projections.
      </p>
    </div>
  {:else}
    <!-- Navigation Tab Bar -->
    <div class="border-b border-stroke/60 flex gap-1 overflow-x-auto">
      {#each tabs as tab}
        <TabButton
          active={activeTab === tab.id}
          onClick={() => setActiveTab(tab.id)}
        >
          {tab.label}
        </TabButton>
      {/each}
    </div>

    <!-- Forecast Above-The-Fold Layout: Election Summary -->
    <div
      class="bg-surface/60 border border-stroke rounded-2xl p-6 shadow-sm backdrop-blur-md animate-fade-in"
    >
      <div class="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        <!-- Left Column: Summary -->
        <div class="lg:col-span-6 flex flex-col space-y-6">
          <div class="space-y-2">
            <div class="flex items-center justify-between">
              <h2 class="text-2xl font-black text-content tracking-tight">
                2026 {activeTab === "house"
                  ? "House"
                  : activeTab === "senate"
                    ? "Senate"
                    : "Governor"} Election Summary
              </h2>
            </div>

            <div class="flex flex-wrap items-center gap-1.5">
              <!-- Control Status Badge -->
              <span
                class="inline-flex items-center gap-1.5 px-3 py-1 rounded-xl text-xs font-extrabold shadow-sm border
              {controlParty === 'Democratic'
                  ? 'bg-blue-500/10 text-blue-700 border-blue-500/20 dark:bg-blue-950/40 dark:text-blue-300 dark:border-blue-900/40'
                  : controlParty === 'Republican'
                    ? 'bg-red-500/10 text-red-700 border-red-500/20 dark:bg-red-950/40 dark:text-red-300 dark:border-red-900/40'
                    : 'bg-slate-500/10 text-slate-700 border-slate-500/20 dark:bg-slate-800/40 dark:text-slate-300 dark:border-slate-700/40'}"
              >
                <span
                  class="w-2 h-2 rounded-full
                {controlParty === 'Democratic'
                    ? 'bg-blue-600 dark:bg-blue-500 animate-pulse'
                    : controlParty === 'Republican'
                      ? 'bg-red-600 dark:bg-red-500 animate-pulse'
                      : 'bg-slate-500 dark:bg-slate-400'}"
                ></span>
                {#if controlParty === "Other"}
                  No clear control projected
                {:else}
                  {controlParty} control projected
                  {#if chamberSummary?.control_probability}
                    ({probability(chamberSummary.control_probability)})
                  {/if}
                {/if}
              </span>

              <!-- VP Tie-break Note -->
              {#if activeTab === "senate" && chamberSummary?.vp_tiebreak_party}
                <span
                  class="text-[10px] text-content-subtle font-semibold bg-surface-alt px-2.5 py-0.5 rounded-full border border-stroke/60 italic"
                >
                  Includes 50-50 tie-break via VP
                </span>
              {/if}
            </div>
          </div>

          <!-- Probability Stat Cards -->
          <div class="grid grid-cols-3 gap-3">
            <!-- Control Probability -->
            <div
              class="bg-surface-alt/30 border border-stroke/40 rounded-xl p-3 text-center backdrop-blur-sm"
            >
              <div
                class="text-[9px] font-bold uppercase text-content-subtle tracking-wider mb-1"
              >
                Control Prob.
              </div>
              <div
                class={`text-xl font-black tabular-nums ${
                  controlParty === "Democratic"
                    ? "text-blue-600 dark:text-blue-400"
                    : controlParty === "Republican"
                      ? "text-red-600 dark:text-red-400"
                      : "text-content"
                }`}
              >
                {probability(chamberSummary?.control_probability)}
              </div>
              <div class="text-[10px] font-semibold text-content-muted mt-0.5">
                {controlParty}
              </div>
            </div>

            <!-- Most Likely Outcome -->
            <div
              class="bg-surface-alt/30 border border-stroke/40 rounded-xl p-3 text-center backdrop-blur-sm"
            >
              <div
                class="text-[9px] font-bold uppercase text-content-subtle tracking-wider mb-1"
              >
                Most Likely Exact Split
              </div>
              <div class="text-xl font-black text-content tabular-nums">
                {mostLikelyOutcome.key || "—"}
              </div>
              <div class="text-[10px] font-semibold text-content-muted mt-0.5">
                {mostLikelyOutcome.probability
                  ? `${(mostLikelyOutcome.probability * 100).toFixed(1)}% chance of this split`
                  : ""}
              </div>
            </div>

            <!-- Competitive Races -->
            <div
              class="bg-surface-alt/30 border border-stroke/40 rounded-xl p-3 text-center backdrop-blur-sm"
            >
              <div
                class="text-[9px] font-bold uppercase text-content-subtle tracking-wider mb-1"
              >
                Battlegrounds
              </div>
              <div
                class="text-xl font-black text-yellow-600 dark:text-yellow-400 tabular-nums"
              >
                {chamberSummary?.tossup_count ?? 0}
              </div>
              <div class="text-[10px] font-semibold text-content-muted mt-0.5">
                toss-ups / {chamberSummary?.competitive_race_count ?? 0} competitive
              </div>
            </div>
          </div>
          <p class="text-xs leading-5 text-content-subtle">
            The exact split is the single most likely outcome in the model's
            distribution. Projected seats summarize each party's model-wide seat
            estimate, so the two figures can differ.
          </p>
        </div>

        <!-- Right Column: Charts / Stats -->
        <div
          class="lg:col-span-6 flex flex-col space-y-6 bg-surface-alt/25 border border-stroke/60 rounded-2xl p-6"
        >
          <!-- Control Probability Panel -->
          <div class="space-y-3">
            <div class="flex items-center justify-between">
              <span
                class="text-xs font-bold uppercase text-content-subtle tracking-wider font-semibold"
                >{activeTab === "governors"
                  ? "Control Probabilities"
                  : "Chamber Control Probabilities"}</span
              >
              {#if activeTab === "senate" && outcomeProbabilities?.tie_50_50}
                <span
                  class="text-[10px] font-semibold text-content-subtle bg-surface-alt px-2 py-0.5 rounded-md border border-stroke/60"
                >
                  50-50 Tie: {probability(outcomeProbabilities.tie_50_50)}
                </span>
              {/if}
            </div>

            {#if outcomeProbabilities}
              {@const demProb = outcomeProbabilities.Democratic ?? 0}
              {@const gopProb = outcomeProbabilities.Republican ?? 0}
              {@const tieProb = outcomeProbabilities.tie_50_50 ?? 0}
              {@const otherProb = outcomeProbabilities.Other ?? 0}
              <div class="space-y-3">
                <div
                  class="h-8 rounded-xl overflow-hidden bg-surface-alt flex border border-stroke/60 relative shadow-inner"
                >
                  {#if demProb > 0}
                    <div
                      class="bg-blue-600 dark:bg-blue-500 transition-all duration-500 flex items-center justify-center font-black text-white text-xs"
                      style="width: {demProb * 100}%"
                      title="Democratic control probability: {probability(
                        demProb,
                      )}"
                    >
                      {#if demProb > 0.15}
                        Democratic {probability(demProb)}
                      {/if}
                    </div>
                  {/if}
                  {#if activeTab === "governors" && tieProb > 0}
                    <div
                      class="bg-slate-400 dark:bg-slate-500 transition-all duration-500 flex items-center justify-center font-black text-white text-xs"
                      style="width: {tieProb * 100}%"
                      title="Split / Tie probability: {probability(tieProb)}"
                    >
                      {#if tieProb > 0.15}
                        Tie {probability(tieProb)}
                      {/if}
                    </div>
                  {/if}
                  {#if otherProb > 0}
                    <div
                      class="bg-slate-400 dark:bg-slate-500 transition-all duration-500 flex items-center justify-center font-black text-white text-xs"
                      style="width: {otherProb * 100}%"
                      title="Other control probability: {probability(
                        otherProb,
                      )}"
                    >
                      {#if otherProb > 0.15}
                        Other {probability(otherProb)}
                      {/if}
                    </div>
                  {/if}
                  {#if gopProb > 0}
                    <div
                      class="bg-red-600 dark:bg-red-500 transition-all duration-500 flex items-center justify-center font-black text-white text-xs ml-auto"
                      style="width: {gopProb * 100}%"
                      title="Republican control probability: {probability(
                        gopProb,
                      )}"
                    >
                      {#if gopProb > 0.15}
                        Republican {probability(gopProb)}
                      {/if}
                    </div>
                  {/if}
                </div>

                <!-- Callout Note -->
                {#if activeTab === "senate" && outcomeProbabilities.tie_50_50 && !(projectedSeats.Democratic === 50 && projectedSeats.Republican === 50)}
                  <div
                    class="bg-surface-alt/40 border border-stroke/60 rounded-xl p-3 flex items-start gap-2.5"
                  >
                    <svg
                      class="w-5 h-5 text-content-subtle shrink-0 mt-0.5"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                      viewBox="0 0 24 24"
                    >
                      <circle cx="12" cy="12" r="10" />
                      <line x1="12" y1="16" x2="12" y2="12" />
                      <line x1="12" y1="8" x2="12.01" y2="8" />
                    </svg>
                    <p
                      class="text-xs text-content-muted leading-relaxed font-medium"
                    >
                      A {probability(outcomeProbabilities.tie_50_50)} 50-50 tie probability
                      is counted as Republican control via VP tie-break, contributing
                      to the Republican control advantage shown above.
                    </p>
                  </div>
                {/if}
              </div>
            {/if}
          </div>

          <!-- Seats Projection Bar -->
          <div class="space-y-3">
            <div class="flex items-center justify-between">
              <span
                class="text-xs font-bold uppercase text-content-subtle tracking-wider font-semibold"
                >Projected Seats</span
              >
            </div>

            <div class="space-y-2">
              <div class="relative pt-4">
                <div
                  class="h-8 rounded-xl overflow-hidden bg-surface-alt flex border border-stroke/60 shadow-inner"
                >
                  <!-- Dem segment -->
                  <div
                    class="bg-blue-600 dark:bg-blue-500 transition-all duration-500 flex items-center justify-center text-xs font-black text-white"
                    style="width: {((projectedSeats.Democratic ?? 0) /
                      totalSeats) *
                      100}%"
                  >
                    {#if (projectedSeats.Democratic ?? 0) > totalSeats * 0.12}
                      D: {projectedSeats.Democratic}
                    {/if}
                  </div>
                  <!-- Other segment -->
                  {#if projectedSeats.Other}
                    <div
                      class="bg-slate-400 dark:bg-slate-500 transition-all duration-500 flex items-center justify-center text-xs font-black text-white"
                      style="width: {((projectedSeats.Other ?? 0) /
                        totalSeats) *
                        100}%"
                    >
                      {#if (projectedSeats.Other ?? 0) > totalSeats * 0.05}
                        {projectedSeats.Other}
                      {/if}
                    </div>
                  {/if}
                  <!-- Rep segment -->
                  <div
                    class="bg-red-600 dark:bg-red-500 transition-all duration-500 flex items-center justify-center text-xs font-black text-white ml-auto"
                    style="width: {((projectedSeats.Republican ?? 0) /
                      totalSeats) *
                      100}%"
                  >
                    {#if (projectedSeats.Republican ?? 0) > totalSeats * 0.12}
                      R: {projectedSeats.Republican}
                    {/if}
                  </div>
                </div>

                <!-- Threshold Marker Line -->
                <div
                  class="absolute top-0 bottom-0 w-0.5 bg-yellow-500 dark:bg-yellow-400 z-10"
                  style="left: {(threshold / totalSeats) * 100}%"
                >
                  <span
                    class="absolute bottom-full left-0 ml-0.5 bg-yellow-500 dark:bg-yellow-400 text-[8px] font-black text-white dark:text-slate-950 px-1 py-0.5 rounded shadow-sm whitespace-nowrap animate-fade-in"
                  >
                    Majority ({threshold})
                  </span>
                </div>

                <!-- Senate 50-50 Line -->
                {#if activeTab === "senate"}
                  <div
                    class="absolute top-0 bottom-0 border-l border-dashed border-slate-400/80 dark:border-slate-500/80 z-10"
                    style="left: 50%"
                  >
                    <span
                      class="absolute top-full right-0 mr-0.5 bg-slate-500 text-[8px] font-black text-white px-1 py-0.5 rounded shadow-sm whitespace-nowrap animate-fade-in"
                    >
                      50-50 Split
                    </span>
                  </div>
                {/if}
              </div>
            </div>
          </div>
        </div>

        <!-- Full-Width Bottom Row: Forecast Overview -->
        <div class="lg:col-span-12 space-y-4 pt-2">
          <div
            class="bg-surface-alt/10 border border-stroke/40 rounded-2xl p-5 relative overflow-hidden"
          >
            <div
              class="flex items-center gap-1.5 text-[10px] font-black uppercase text-blue-600 dark:text-blue-400 tracking-wider mb-2.5"
            >
              <svg
                class="w-3.5 h-3.5"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"
                />
              </svg>
              Forecast Overview
            </div>
            <p class="text-sm font-semibold text-content leading-relaxed">
              {chamberNarrative ||
                "Projections indicate a highly competitive cycle for this chamber."}
            </p>
          </div>

          <!-- Clean Updated Footer -->
          <div
            class="flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] text-content-subtle font-semibold px-1"
          >
            <span>AI-generated model projection</span>
            {#if chamberForecasts?.updated_at}
              <span class="w-1 h-1 rounded-full bg-stroke/60"></span>
              <span
                >Last updated <span class="font-bold text-content"
                  >{new Date(
                    chamberForecasts.updated_at,
                  ).toLocaleDateString()}</span
                ></span
              >
            {/if}
          </div>
        </div>
      </div>
    </div>

    <!-- Interactive Map & Statistics Dashboard Grid -->
    <section
      class="grid grid-cols-1 lg:grid-cols-[minmax(0,1.3fr)_minmax(320px,0.7fr)] gap-6 items-stretch"
    >
      <!-- Map Canvas Card -->
      <div
        class="bg-surface/60 border border-stroke rounded-2xl p-6 shadow-sm backdrop-blur-md flex flex-col min-h-[380px] h-full"
      >
        <div
          class="flex items-center justify-between border-b border-stroke/40 pb-4 mb-4"
        >
          <div>
            <h2 class="text-lg font-bold text-content">Electoral Map</h2>
            <p class="text-xs text-content-subtle">
              Shaded by projected rating or holdover representation
            </p>
          </div>
          {#if selectedState}
            <button
              on:click={clearStateFilter}
              class="text-xs text-blue-600 hover:text-blue-500 dark:text-blue-400 dark:hover:text-blue-300 font-semibold flex items-center gap-1 bg-blue-50 dark:bg-blue-950/40 px-2.5 py-1 rounded-lg border border-blue-200/50 dark:border-blue-900/50"
            >
              Clear Map Filter: {selectedState} x
            </button>
          {/if}
        </div>

        <div
          class="relative w-full py-2 flex flex-1 items-center justify-center min-h-[320px]"
        >
          <USMap
            {activeStates}
            {selectedState}
            raceCounts={stateRaceCounts}
            {stateColors}
            {stateTooltips}
            on:stateClick={handleStateClick}
          />
        </div>

        <!-- Map Colors Legend -->
        <div class="border-t border-stroke/40 pt-4 mt-4 space-y-3">
          <span class="text-xs font-semibold text-content-muted block"
            >Map Legend</span
          >
          <div
            class="flex flex-wrap gap-x-4 gap-y-2 justify-center lg:justify-start"
          >
            <div class="flex items-center gap-1.5 text-xs text-content-muted">
              <span
                class="w-3.5 h-3.5 rounded bg-blue-700 block border border-blue-950/10"
              ></span> Safe D
            </div>
            <div class="flex items-center gap-1.5 text-xs text-content-muted">
              <span
                class="w-3.5 h-3.5 rounded bg-blue-400 block border border-blue-950/10"
              ></span> Likely D
            </div>
            <div class="flex items-center gap-1.5 text-xs text-content-muted">
              <span
                class="w-3.5 h-3.5 rounded bg-blue-200 block border border-blue-950/10"
              ></span> Lean/Tilt D
            </div>
            <div class="flex items-center gap-1.5 text-xs text-content-muted">
              <span
                class="w-3.5 h-3.5 rounded bg-slate-200 dark:bg-slate-700 block border border-slate-900/10"
              ></span> Toss-up
            </div>
            <div class="flex items-center gap-1.5 text-xs text-content-muted">
              <span
                class="w-3.5 h-3.5 rounded bg-red-200 block border border-red-950/10"
              ></span> Lean/Tilt R
            </div>
            <div class="flex items-center gap-1.5 text-xs text-content-muted">
              <span
                class="w-3.5 h-3.5 rounded bg-red-400 block border border-red-950/10"
              ></span> Likely R
            </div>
            <div class="flex items-center gap-1.5 text-xs text-content-muted">
              <span
                class="w-3.5 h-3.5 rounded bg-red-700 block border border-red-950/10"
              ></span> Safe R
            </div>
            {#if activeTab !== "house"}
              <div class="flex items-center gap-1.5 text-xs text-content-muted">
                <span
                  class="w-3.5 h-3.5 rounded block border border-blue-500/30 border-dashed"
                  style="background-color: var(--color-holdover-d);"
                ></span> Dem Holdover
              </div>
              <div class="flex items-center gap-1.5 text-xs text-content-muted">
                <span
                  class="w-3.5 h-3.5 rounded block border border-red-500/30 border-dashed"
                  style="background-color: var(--color-holdover-r);"
                ></span> GOP Holdover
              </div>
            {/if}
          </div>
        </div>
      </div>

      <!-- Stats Panel Column -->
      <div class="space-y-6 h-full flex flex-col">
        <!-- Projection Summary Stat Card -->
        <div
          class="bg-surface/60 border border-stroke rounded-2xl p-6 shadow-sm backdrop-blur-md"
        >
          <p
            class="text-xs font-bold uppercase text-content-subtle tracking-wider"
          >
            {aggregate.label} Projected Seats
          </p>

          <h3
            class="mt-3 text-3xl font-extrabold text-content flex items-baseline gap-2"
          >
            <span class={partyClass(controlParty)}>
              {controlParty === "Other"
                ? "No Clear Control"
                : `${controlParty} Control`}
            </span>
          </h3>

          <p class="mt-1 text-xs text-content-subtle font-medium">
            {chamberSummary?.threshold ?? aggregate.threshold} seats needed for majority
          </p>

          <!-- Seat Distribution Bar Chart -->
          <div class="mt-6 space-y-1.5">
            <div
              class="flex items-center justify-between text-xs font-bold text-content-muted"
            >
              <span>Democrat: {projectedSeats.Democratic ?? 0}</span>
              <span>Republican: {projectedSeats.Republican ?? 0}</span>
            </div>

            <div
              class="h-6 rounded-full overflow-hidden bg-surface-alt flex border border-stroke/60"
            >
              <div
                class="bg-blue-600 dark:bg-blue-500 transition-all duration-500 flex items-center justify-center text-[10px] font-bold text-white shadow-inner"
                style={`width: ${Math.min(
                  100,
                  ((projectedSeats.Democratic ?? 0) / aggregate.totalExpected) *
                    100,
                )}%`}
                title="Democratic projected seats"
              >
                {#if (projectedSeats.Democratic ?? 0) > 20}
                  {projectedSeats.Democratic}
                {/if}
              </div>
              {#if projectedSeats.Other}
                <div
                  class="bg-slate-400 dark:bg-slate-500 transition-all duration-500 flex items-center justify-center text-[10px] font-bold text-white shadow-inner"
                  style={`width: ${Math.min(
                    100,
                    ((projectedSeats.Other ?? 0) / aggregate.totalExpected) *
                      100,
                  )}%`}
                  title="Other projected seats"
                >
                  {#if (projectedSeats.Other ?? 0) > aggregate.totalExpected * 0.05}
                    {projectedSeats.Other}
                  {/if}
                </div>
              {/if}
              <div
                class="bg-red-600 dark:bg-red-500 transition-all duration-500 flex items-center justify-center text-[10px] font-bold text-white shadow-inner ml-auto"
                style={`width: ${Math.min(
                  100,
                  ((projectedSeats.Republican ?? 0) / aggregate.totalExpected) *
                    100,
                )}%`}
                title="Republican projected seats"
              >
                {#if (projectedSeats.Republican ?? 0) > 20}
                  {projectedSeats.Republican}
                {/if}
              </div>
            </div>

            <div
              class="flex justify-between text-[10px] text-content-subtle px-1"
            >
              <span>Total: {aggregate.totalExpected}</span>
              <span
                >Majority Line: {chamberSummary?.threshold ??
                  aggregate.threshold}</span
              >
            </div>
            {#if outcomeProbabilities}
              <div class="mt-4 grid grid-cols-2 gap-2 text-xs">
                <div
                  class="rounded-lg border border-blue-500/20 bg-blue-500/10 px-3 py-2"
                >
                  <div class="font-bold text-blue-700 dark:text-blue-300">
                    {probability(outcomeProbabilities.Democratic)}
                  </div>
                  <div
                    class="text-[10px] text-content-subtle font-semibold uppercase tracking-wider"
                  >
                    Dem control
                  </div>
                </div>
                <div
                  class="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-right"
                >
                  <div class="font-bold text-red-700 dark:text-red-300">
                    {probability(outcomeProbabilities.Republican)}
                  </div>
                  <div
                    class="text-[10px] text-content-subtle font-semibold uppercase tracking-wider"
                  >
                    GOP control
                  </div>
                </div>
              </div>
            {/if}
            {#if expectedSeats}
              <p class="mt-3 text-[10px] text-content-subtle">
                Expected seats: D {oneDecimal(expectedSeats.Democratic)}, R {oneDecimal(
                  expectedSeats.Republican,
                )}
                {#if expectedSeats.Other}
                  , Other {oneDecimal(expectedSeats.Other)}
                {/if}
              </p>
            {/if}
          </div>

          <!-- Net Seats Change Grid -->
          <div
            class="mt-6 pt-5 border-t border-stroke/40 grid grid-cols-3 gap-3"
          >
            {#each controlParties as party}
              <div
                class="bg-surface-alt/40 border border-stroke/40 rounded-xl px-2.5 py-2 text-center shadow-inner"
              >
                <div
                  class="text-[10px] text-content-subtle font-bold uppercase tracking-wider"
                >
                  {party.slice(0, 3)}
                </div>
                <div class={`text-xl font-black mt-1 ${partyClass(party)}`}>
                  {projectedSeats[party] ?? 0}
                </div>
                <div
                  class="text-[10px] text-content-subtle font-semibold tabular-nums mt-0.5"
                >
                  {formatNet(aggregate.netChange[party] ?? 0)} net
                </div>
              </div>
            {/each}
          </div>
        </div>

        {#if chamberSummary?.seat_distribution && Object.keys(chamberSummary.seat_distribution).length > 0}
          <!-- Seat Outcome Distribution Card -->
          <div
            class="bg-surface/60 border border-stroke rounded-2xl p-6 shadow-sm backdrop-blur-md flex-1"
          >
            <div
              class="flex items-center justify-between mb-4 border-b border-stroke/40 pb-3"
            >
              <div>
                <h3
                  class="text-sm font-black uppercase text-content-subtle tracking-wider"
                >
                  Seat Outcome Distribution
                </h3>
                <p class="text-[10px] text-content-subtle font-medium mt-0.5">
                  Probability of final Republican/Democratic seat splits
                </p>
              </div>
            </div>

            <!-- Chart Tab Toggle -->
            <div
              class="flex gap-1 bg-surface-alt/60 p-1 rounded-lg border border-stroke/45 mb-4"
            >
              <button
                on:click={() => (activeChartType = "buckets")}
                class={`flex-1 text-center py-1 text-[11px] font-bold rounded-md transition-all ${
                  activeChartType === "buckets"
                    ? "bg-surface text-content shadow-sm border border-stroke/20"
                    : "text-content-subtle hover:text-content"
                }`}
              >
                Groups
              </button>
              <button
                on:click={() => (activeChartType = "histogram")}
                class={`flex-1 text-center py-1 text-[11px] font-bold rounded-md transition-all ${
                  activeChartType === "histogram"
                    ? "bg-surface text-content shadow-sm border border-stroke/20"
                    : "text-content-subtle hover:text-content"
                }`}
              >
                Histogram
              </button>
              <button
                on:click={() => (activeChartType = "curve")}
                class={`flex-1 text-center py-1 text-[11px] font-bold rounded-md transition-all ${
                  activeChartType === "curve"
                    ? "bg-surface text-content shadow-sm border border-stroke/20"
                    : "text-content-subtle hover:text-content"
                }`}
              >
                Curve
              </button>
            </div>

            <!-- Chart Content Area -->
            <div class="min-h-[160px] flex flex-col justify-center">
              {#if activeChartType === "buckets"}
                <div class="space-y-4">
                  <!-- Visual Stacked Bar -->
                  <div
                    class="h-8 rounded-lg overflow-hidden flex border border-stroke/60"
                  >
                    {#each seatBuckets as bucket}
                      {#if bucket.probability > 0}
                        <div
                          class={`${bucket.colorClass} transition-all duration-500 flex items-center justify-center text-[10px] font-bold text-white shadow-inner relative group cursor-pointer`}
                          style={`width: ${bucket.probability * 100}%`}
                        >
                          <!-- Tooltip -->
                          <div
                            class="absolute bottom-full mb-2 hidden group-hover:block z-50 bg-surface border border-stroke p-2 rounded-lg shadow-md text-xs font-semibold text-content w-40 text-center pointer-events-none"
                          >
                            <div class="font-bold">{bucket.label}</div>
                            <div class="text-blue-600 dark:text-blue-400 mt-1">
                              {(bucket.probability * 100).toFixed(1)}%
                              probability
                            </div>
                          </div>

                          {#if bucket.probability > 0.08}
                            {Math.round(bucket.probability * 100)}%
                          {/if}
                        </div>
                      {/if}
                    {/each}
                  </div>

                  <!-- Legend & Details -->
                  <div class="grid grid-cols-1 gap-2.5">
                    {#each seatBuckets as bucket}
                      {#if bucket.probability > 0}
                        <div class="flex items-center justify-between text-xs">
                          <div class="flex items-center gap-2">
                            <span
                              class={`w-3.5 h-3.5 rounded ${bucket.colorClass} border border-stroke/20`}
                            ></span>
                            <span class="font-bold text-content"
                              >{bucket.label}</span
                            >
                          </div>
                          <span class="font-black text-content-muted"
                            >{(bucket.probability * 100).toFixed(1)}%</span
                          >
                        </div>
                      {/if}
                    {/each}
                  </div>
                </div>
              {:else if activeChartType === "histogram"}
                <div
                  class="space-y-2 max-h-[280px] overflow-y-auto pr-1 select-none"
                >
                  {#each sortedOutcomes as outcome}
                    {@const isTie = outcome.dSeats === 50}
                    {@const isDem = outcome.dSeats >= 51}
                    <div class="flex items-center gap-3 text-xs">
                      <!-- Label e.g. "52D - 48R" -->
                      <span
                        class="w-18 font-mono font-bold text-[10px] text-content-subtle shrink-0"
                      >
                        {outcome.dSeats}D - {outcome.rSeats}R
                      </span>
                      <!-- Bar track -->
                      <div
                        class="flex-1 bg-surface-alt rounded-full h-3 overflow-hidden border border-stroke/40 relative"
                      >
                        <div
                          class={`h-full rounded-full transition-all duration-300 ${
                            isTie
                              ? "bg-slate-400 dark:bg-slate-500"
                              : isDem
                                ? "bg-blue-500 dark:bg-blue-600"
                                : "bg-red-500 dark:bg-red-600"
                          }`}
                          style={`width: ${
                            (outcome.probability / maxProbability) * 100
                          }%`}
                        ></div>
                      </div>
                      <!-- Value -->
                      <span
                        class="w-10 text-right font-black font-mono text-[10px] text-content-muted shrink-0"
                      >
                        {(outcome.probability * 100).toFixed(1)}%
                      </span>
                    </div>
                  {/each}
                </div>
              {:else if activeChartType === "curve"}
                <div
                  class="relative w-full h-[180px] select-none flex flex-col justify-between"
                >
                  <!-- SVG Area Chart -->
                  <svg
                    viewBox="0 0 300 100"
                    class="w-full h-[140px] overflow-visible"
                  >
                    <defs>
                      <linearGradient
                        id="curveGradient"
                        x1="0"
                        y1="0"
                        x2="0"
                        y2="1"
                      >
                        <stop
                          offset="0%"
                          stop-color="rgba(59, 130, 246, 0.4)"
                        />
                        <stop
                          offset="100%"
                          stop-color="rgba(239, 68, 68, 0.4)"
                        />
                      </linearGradient>
                      <linearGradient
                        id="lineGradient"
                        x1="0"
                        y1="0"
                        x2="1"
                        y2="0"
                      >
                        <stop offset="0%" stop-color="#3b82f6" />
                        <stop offset="100%" stop-color="#ef4444" />
                      </linearGradient>
                    </defs>

                    <!-- Grid lines -->
                    <line
                      x1="15"
                      y1="85"
                      x2="285"
                      y2="85"
                      stroke="currentColor"
                      class="text-stroke/60"
                      stroke-width="0.75"
                    />
                    <line
                      x1="15"
                      y1="10"
                      x2="285"
                      y2="10"
                      stroke="currentColor"
                      class="text-stroke/20"
                      stroke-dasharray="2 2"
                      stroke-width="0.5"
                    />

                    <!-- Area Path -->
                    {#if svgData.fillPath}
                      <path d={svgData.fillPath} fill="url(#curveGradient)" />
                      <path
                        d={svgData.strokePath}
                        stroke="url(#lineGradient)"
                        stroke-width="1.5"
                        fill="none"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                      />
                    {/if}

                    <!-- Tie break line -->
                    <line
                      x1={svgData.tieX}
                      y1="10"
                      x2={svgData.tieX}
                      y2="85"
                      stroke="currentColor"
                      class="text-slate-400 dark:text-slate-500"
                      stroke-width="1"
                      stroke-dasharray="3 3"
                    />

                    <!-- Hoverable Points -->
                    {#each svgData.points as pt}
                      <g class="group/point cursor-pointer">
                        <circle
                          cx={pt.x}
                          cy={pt.y}
                          r="3.5"
                          fill="currentColor"
                          class="text-blue-600 dark:text-blue-400 scale-0 group-hover/point:scale-120 transition-transform origin-center"
                          stroke="currentColor"
                          stroke-width="1.5"
                        />
                        <circle cx={pt.x} cy={pt.y} r="7" fill="transparent" />
                        <foreignObject
                          x={Math.max(10, pt.x - 55)}
                          y={Math.max(0, pt.y - 38)}
                          width="110"
                          height="35"
                          class="pointer-events-none hidden group-hover/point:block overflow-visible z-50"
                        >
                          <div
                            class="bg-surface border border-stroke p-1 rounded shadow-md text-[8px] font-black text-center leading-tight"
                          >
                            <div>{pt.dSeats}D - {pt.rSeats}R</div>
                            <div class="text-blue-500 mt-0.5">
                              {(pt.prob * 100).toFixed(1)}% prob
                            </div>
                          </div>
                        </foreignObject>
                      </g>
                    {/each}
                  </svg>

                  <!-- X-axis Labels -->
                  <div
                    class="flex justify-between text-[9px] font-bold text-content-subtle px-2 border-t border-stroke/20 pt-1.5 mt-1"
                  >
                    <span>{svgData.minD}D (Min)</span>
                    <span class="text-slate-400 dark:text-slate-500"
                      >50-50 Tie Threshold</span
                    >
                    <span>{svgData.maxD}D (Max)</span>
                  </div>
                </div>
              {/if}
            </div>
          </div>
        {/if}
      </div>
    </section>

    <!-- Ratings Counts Grid Card -->
    <section
      class="bg-surface/60 border border-stroke rounded-2xl p-6 shadow-sm backdrop-blur-md"
    >
      <p
        class="text-xs font-bold uppercase text-content-subtle tracking-wider mb-4"
      >
        Forecast Ratings Breakdown
      </p>
      <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-9 gap-2">
        {#each ratingOrder as rating}
          <div
            class={`border rounded-xl px-2 py-1.5 text-center transition-all ${ratingClass(
              rating,
            )}`}
          >
            <div class="text-[10px] font-bold leading-tight truncate">
              {formatRating(rating)}
            </div>
            <div class="text-lg font-black mt-1 tabular-nums">
              {aggregate.ratingCounts[rating] ?? 0}
            </div>
          </div>
        {/each}
      </div>
    </section>

    <!-- Races That Matter Most â€” Horizontal Scroll Strip -->
    {#if keyRacesList.length > 0}
      <section class="space-y-4">
        <div
          class="flex items-center justify-between border-b border-stroke/20 pb-2"
        >
          <h3 class="text-base font-bold uppercase text-content tracking-wider">
            Races That Matter Most
          </h3>
          <div class="flex items-center gap-2">
            <span
              class="text-xs text-content-subtle font-semibold hidden sm:inline"
            >
              Key battlegrounds driving chamber control
            </span>
            <button
              on:click={() => scrollKeyRaces(-1)}
              class="h-11 w-11 rounded-lg border border-stroke/60 bg-surface hover:bg-surface-alt flex items-center justify-center text-content-subtle hover:text-content transition-colors"
              aria-label="Scroll left"
            >
              <svg
                class="w-4 h-4"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  d="M15 19l-7-7 7-7"
                />
              </svg>
            </button>
            <button
              on:click={() => scrollKeyRaces(1)}
              class="h-11 w-11 rounded-lg border border-stroke/60 bg-surface hover:bg-surface-alt flex items-center justify-center text-content-subtle hover:text-content transition-colors"
              aria-label="Scroll right"
            >
              <svg
                class="w-4 h-4"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  d="M9 5l7 7-7 7"
                />
              </svg>
            </button>
          </div>
        </div>

        <div
          bind:this={keyRacesContainer}
          class="flex gap-4 overflow-x-auto pb-3 scroll-smooth snap-x snap-mandatory hide-scrollbar"
          style="-ms-overflow-style: none; scrollbar-width: none;"
        >
          {#each keyRacesList as race}
            {@const rating = race.forecast?.rating}
            {@const ratingBorderColor = rating
              ? rating.endsWith("_d")
                ? "border-l-blue-500"
                : rating.endsWith("_r")
                  ? "border-l-red-500"
                  : "border-l-yellow-500"
              : "border-l-slate-400"}
            <div
              class={`snap-start shrink-0 w-[300px] bg-surface border border-stroke rounded-xl p-4 shadow-sm hover:shadow-md transition-all border-l-[3px] ${ratingBorderColor}`}
            >
              <div class="flex items-center justify-between mb-2">
                <a
                  href={browser ? raceHref(race.id) : undefined}
                  class="inline-flex min-h-11 items-center font-black text-sm text-content hover:text-blue-600 dark:hover:text-blue-400 truncate"
                >
                  {race.state ||
                    race.title?.replace("2026 U.S. Senate election in ", "")}
                </a>
                {#if rating}
                  <span
                    class={`text-[10px] font-extrabold uppercase px-2 py-0.5 rounded-full border shrink-0 ml-2 ${ratingClass(
                      rating,
                    )}`}
                  >
                    {formatRating(rating)}
                  </span>
                {/if}
              </div>

              {#if race.forecast}
                <div class="flex items-center gap-3 mb-2">
                  <span class="text-xs font-bold text-content tabular-nums">
                    {probability(race.forecast.win_probability)} win
                  </span>
                  {#if race.forecast.margin_estimate !== undefined && race.forecast.margin_estimate !== null}
                    <span
                      class="text-[10px] text-content-subtle font-semibold tabular-nums"
                    >
                      {race.forecast.margin_estimate > 0
                        ? "+"
                        : ""}{race.forecast.margin_estimate.toFixed(1)}% margin
                    </span>
                  {/if}
                </div>
              {/if}

              <p
                class="text-[11px] text-content-muted leading-relaxed font-medium line-clamp-2"
              >
                {race.forecast?.takeaway ||
                  race.forecast?.rationale?.split(/[.!?]/)[0] + "." ||
                  "No takeaway available."}
              </p>

              <div class="mt-3 pt-2 border-t border-stroke/30">
                <a
                  href={browser ? raceHref(race.id) : undefined}
                  class="inline-flex min-h-11 items-center text-xs text-blue-600 dark:text-blue-400 font-bold hover:underline"
                >
                  View Details &rarr;
                </a>
              </div>
            </div>
          {/each}
        </div>
      </section>
    {/if}

    <!-- Outlook & Analysis Section -->
    <section class="space-y-4">
      <div
        class="flex items-center justify-between border-b border-stroke/20 pb-2"
      >
        <h3 class="text-base font-bold uppercase text-content tracking-wider">
          Outlook & Analysis
        </h3>
        <span class="text-xs text-content-subtle font-semibold"
          >Structured assessment of the {activeTab === "house"
            ? "House"
            : activeTab === "senate"
              ? "Senate"
              : "Governor"} map</span
        >
      </div>

      {#if chamberSummary?.bottom_line || chamberSummary?.why_party_favored || chamberSummary?.opposing_party_path || chamberSummary?.key_uncertainty}
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <!-- Bottom Line -->
          {#if chamberSummary.bottom_line}
            <div
              class="bg-surface/80 border-2 border-blue-500/30 dark:border-blue-500/20 rounded-2xl p-5 shadow-sm relative overflow-hidden backdrop-blur-md"
            >
              <div
                class="absolute top-0 right-0 w-24 h-24 bg-blue-500/5 dark:bg-blue-500/10 rounded-bl-full pointer-events-none"
              ></div>
              <h4
                class="text-xs font-black uppercase text-blue-600 dark:text-blue-400 tracking-widest mb-2 flex items-center gap-1.5"
              >
                <svg
                  class="w-4 h-4 text-blue-600 dark:text-blue-400 shrink-0"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  viewBox="0 0 24 24"
                >
                  <circle cx="12" cy="12" r="10" />
                  <circle cx="12" cy="12" r="6" />
                  <circle cx="12" cy="12" r="2" />
                </svg> The Bottom Line
              </h4>
              <p class="text-sm font-semibold text-content leading-relaxed">
                {chamberSummary.bottom_line}
              </p>
            </div>
          {/if}

          <!-- Why Favored -->
          {#if chamberSummary.why_party_favored}
            <div
              class="bg-surface/60 border border-stroke rounded-2xl p-5 shadow-sm backdrop-blur-md"
            >
              <h4
                class="text-xs font-black uppercase text-red-600 dark:text-red-400 tracking-widest mb-2 flex items-center gap-1.5"
              >
                <svg
                  class="w-4 h-4 text-red-600 dark:text-red-400 shrink-0"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  viewBox="0 0 24 24"
                >
                  <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
                  <polyline points="16 7 22 7 22 13" />
                </svg>
                Why {chamberSummary.control_party === "Democratic"
                  ? "Democrats"
                  : "Republicans"} Are Favored
              </h4>
              <p
                class="text-xs text-content-muted leading-relaxed font-medium font-semibold"
              >
                {chamberSummary.why_party_favored}
              </p>
            </div>
          {/if}

          <!-- Opposing Path -->
          {#if chamberSummary.opposing_party_path}
            <div
              class="bg-surface/60 border border-stroke rounded-2xl p-5 shadow-sm backdrop-blur-md"
            >
              <h4
                class="text-xs font-black uppercase text-blue-600 dark:text-blue-400 tracking-widest mb-2 flex items-center gap-1.5"
              >
                <svg
                  class="w-4 h-4 text-blue-600 dark:text-blue-400 shrink-0"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  viewBox="0 0 24 24"
                >
                  <circle cx="6" cy="19" r="3" />
                  <path
                    d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15"
                  />
                  <circle cx="18" cy="5" r="3" />
                </svg>
                {chamberSummary.control_party === "Democratic"
                  ? "Republican"
                  : "Democratic"} Path to Control
              </h4>
              <p
                class="text-xs text-content-muted leading-relaxed font-medium font-semibold"
              >
                {chamberSummary.opposing_party_path}
              </p>
            </div>
          {/if}

          <!-- Key Uncertainty -->
          {#if chamberSummary.key_uncertainty}
            <div
              class="bg-surface/60 border border-stroke rounded-2xl p-5 shadow-sm backdrop-blur-md"
            >
              <h4
                class="text-xs font-black uppercase text-yellow-600 dark:text-yellow-400 tracking-widest mb-2 flex items-center gap-1.5"
              >
                <svg
                  class="w-4 h-4 text-yellow-600 dark:text-yellow-400 shrink-0"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  viewBox="0 0 24 24"
                >
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="8" x2="12.01" y2="8" />
                  <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
                  <line x1="12" y1="17" x2="12.01" y2="17" />
                </svg> Key Risk & Uncertainty
              </h4>
              <p
                class="text-xs text-content-muted leading-relaxed font-medium font-semibold"
              >
                {chamberSummary.key_uncertainty}
              </p>
            </div>
          {/if}
        </div>
      {:else}
        <!-- Fallback narrative card -->
        <div
          class="bg-surface/60 border border-stroke rounded-2xl p-6 shadow-sm backdrop-blur-md flex flex-col justify-between"
        >
          <div>
            <p class="text-sm font-medium text-content leading-relaxed">
              {chamberNarrative ||
                `Projections indicate a highly competitive cycle for the ${
                  activeTab === "governors"
                    ? "Governors"
                    : activeTab === "senate"
                      ? "Senate"
                      : "House"
                }.`}
            </p>
          </div>
        </div>
      {/if}
    </section>

    <!-- Active competitive/active races list -->
    <section
      class="bg-surface border border-stroke rounded-2xl shadow-sm overflow-hidden"
    >
      <!-- Filter and Sort Header bar -->
      <div
        class="px-5 py-5 border-b border-stroke/40 bg-surface-alt/10 space-y-4"
      >
        <div class="flex flex-col md:flex-row justify-between gap-4">
          <!-- Pills Filter block -->
          <div class="space-y-2.5">
            <div class="flex flex-wrap items-center gap-2">
              <span
                class="text-xs font-bold text-content-subtle uppercase tracking-wider w-16"
                >Rating:</span
              >
              {#each [{ id: "all", label: "All Ratings" }, { id: "tossup", label: "Toss-ups" }, { id: "tilt", label: "Tilt" }, { id: "lean", label: "Lean" }, { id: "likely_safe", label: "Likely/Safe" }] as pill}
                <button
                  type="button"
                  on:click={() => (filterRating = pill.id)}
                  class="text-xs px-3 py-1.5 rounded-full font-bold transition-all border
                  {filterRating === pill.id
                    ? 'bg-blue-600 text-white border-blue-600 dark:bg-blue-500 dark:border-blue-500'
                    : 'bg-surface border-stroke hover:bg-surface-alt/50 text-content-muted'}"
                >
                  {pill.label}
                </button>
              {/each}
            </div>

            <div class="flex flex-wrap items-center gap-2">
              <span
                class="text-xs font-bold text-content-subtle uppercase tracking-wider w-16"
                >Favored:</span
              >
              {#each [{ id: "all", label: "All Parties" }, { id: "Democratic", label: "Democratic" }, { id: "Republican", label: "Republican" }] as pill}
                <button
                  type="button"
                  on:click={() => (filterParty = pill.id)}
                  class="text-xs px-3 py-1.5 rounded-full font-bold transition-all border
                  {filterParty === pill.id
                    ? pill.id === 'Democratic'
                      ? 'bg-blue-600 text-white border-blue-600 dark:bg-blue-500 dark:border-blue-500'
                      : 'bg-red-600 text-white border-red-600 dark:bg-red-500 dark:border-red-500'
                    : 'bg-surface border-stroke hover:bg-surface-alt/50 text-content-muted'}"
                >
                  {pill.label}
                </button>
              {/each}
            </div>
          </div>

          <!-- Sort block -->
          <div
            class="flex flex-row md:flex-col md:items-end justify-between md:justify-start gap-4"
          >
            <div class="flex items-center gap-2.5">
              <label
                for="sort-by"
                class="text-xs font-bold text-content-subtle uppercase tracking-wider"
                >Sort by:</label
              >
              <select
                id="sort-by"
                bind:value={sortBy}
                class="text-xs bg-surface border border-stroke/60 rounded-xl px-3 py-1.5 text-content font-bold focus:outline-none focus:ring-1 focus:ring-blue-500"
              >
                <option value="control_relevance"
                  >Most likely to decide control</option
                >
                <option value="competitiveness">Most competitive</option>
                <option value="dem_pickup"
                  >Highest Democratic pickup chance</option
                >
                <option value="gop_pickup"
                  >Highest Republican hold/pickup chance</option
                >
                <option value="probability">Win Probability</option>
                <option value="margin">Margin Estimate</option>
                <option value="state">State</option>
                <option value="rating">Rating</option>
              </select>
            </div>

            <div class="flex items-center gap-2.5 text-xs">
              {#if selectedState}
                <button
                  type="button"
                  on:click={clearStateFilter}
                  class="text-xs text-blue-600 hover:text-blue-500 dark:text-blue-400 dark:hover:text-blue-300 font-bold bg-blue-50 dark:bg-blue-950/40 px-2.5 py-1 rounded-xl border border-blue-200/50"
                >
                  State: {selectedState} x
                </button>
              {/if}

              <span
                class="text-xs text-content-subtle font-extrabold bg-surface-alt px-2.5 py-1 rounded-xl border border-stroke/60"
              >
                {filteredRaces.length} races
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Empty state -->
      {#if filteredRaces.length === 0}
        <div class="p-12 text-center">
          <p class="text-base text-content-muted font-semibold">
            No forecasts found matching the selected filters.
          </p>
          {#if selectedState || filterRating !== "all" || filterParty !== "all"}
            <button
              type="button"
              on:click={() => {
                clearStateFilter();
                filterRating = "all";
                filterParty = "all";
              }}
              class="mt-3 text-xs text-blue-600 hover:underline dark:text-blue-400 font-semibold"
            >
              Clear all filters
            </button>
          {/if}
        </div>
      {:else}
        <!-- Responsive Card Feed -->
        <div
          class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 p-4 bg-surface-alt/10"
        >
          {#each sortedRaces.slice(0, visibleRaceCount) as race (race.id)}
            {@const party = normalizeForecastParty(
              race.forecast.predicted_winner_party,
              race.forecast.party_probabilities,
              race.candidates,
            )}
            {@const rating = race.forecast.rating}
            {@const isExpanded = expandedRaceIds.has(race.id)}

            <article
              class="bg-surface border border-stroke/70 rounded-xl p-5 shadow-sm hover:border-blue-400/50 dark:hover:border-blue-500/50 transition-colors flex flex-col justify-between gap-4"
            >
              <div class="space-y-4">
                <!-- Card Header: Title, Rating, and Details Link -->
                <div class="flex flex-col gap-1.5">
                  <div class="flex items-start justify-between gap-2">
                    <a
                      href={browser ? raceHref(race.id) : undefined}
                      class="text-base font-extrabold text-content hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
                    >
                      {race.title ?? race.id}
                    </a>
                    <a
                      href={browser ? raceHref(race.id) : undefined}
                      class="text-[10px] text-content-subtle hover:text-blue-600 dark:hover:text-blue-400 font-extrabold bg-surface border border-stroke/60 px-2 py-0.5 rounded-md transition-all whitespace-nowrap self-start"
                    >
                      Details ->
                    </a>
                  </div>
                  <div class="flex flex-wrap items-center gap-1.5">
                    <span class="text-xs text-content-subtle font-medium">
                      {race.jurisdiction ?? race.state ?? race.office}
                    </span>
                    <span class="w-1 h-1 rounded-full bg-stroke/60"></span>
                    <span
                      class={`inline-flex border rounded-full px-2 py-0.5 text-[10px] font-black leading-none ${ratingClass(
                        rating,
                      )}`}
                    >
                      {formatRating(rating)}
                    </span>
                  </div>
                </div>

                <!-- Card Metrics Dashboard -->
                <div
                  class="grid grid-cols-3 gap-2 bg-surface-alt/30 border border-stroke/40 rounded-xl p-3 text-center"
                >
                  <div
                    class="flex flex-col justify-center border-r border-stroke/30 min-w-0 pr-1"
                  >
                    <span
                      class="text-[9px] font-bold text-content-subtle uppercase tracking-wider"
                      >Projected</span
                    >
                    <span
                      class={`text-xs font-black mt-0.5 leading-tight break-words truncate ${partyClass(
                        party,
                      )}`}
                      title={race.forecast.predicted_winner_name || party}
                    >
                      {race.forecast.predicted_winner_name || party}
                    </span>
                  </div>
                  <div
                    class="flex flex-col justify-center border-r border-stroke/30"
                  >
                    <span
                      class="text-[9px] font-bold text-content-subtle uppercase tracking-wider"
                      >Win Prob.</span
                    >
                    <span
                      class="text-xs font-black mt-0.5 text-content tabular-nums"
                    >
                      {probability(race.forecast.win_probability)}
                    </span>
                  </div>
                  <div class="flex flex-col justify-center pl-1">
                    <span
                      class="text-[9px] font-bold text-content-subtle uppercase tracking-wider"
                      >Est. Margin</span
                    >
                    <span
                      class="text-xs font-black mt-0.5 text-content tabular-nums"
                    >
                      {race.forecast.margin_estimate === undefined ||
                      race.forecast.margin_estimate === null
                        ? "n/a"
                        : `${
                            race.forecast.margin_estimate > 0 ? "+" : ""
                          }${race.forecast.margin_estimate.toFixed(1)}%`}
                    </span>
                  </div>
                </div>

                <!-- D vs R Split details -->
                {#if race.forecast.party_probabilities}
                  <div
                    class="text-[10px] text-content-subtle flex justify-between font-bold px-1.5"
                  >
                    <span class="text-blue-600 dark:text-blue-400"
                      >Dem: {probability(
                        race.forecast.party_probabilities.Democratic,
                      )}</span
                    >
                    <span class="text-red-600 dark:text-red-400"
                      >GOP: {probability(
                        race.forecast.party_probabilities.Republican,
                      )}</span
                    >
                  </div>
                {/if}

                <!-- Takeaway Text -->
                <div
                  class="flex flex-col justify-center border-t border-stroke/20 pt-2.5"
                >
                  <span
                    class="text-[9px] font-bold text-content-subtle uppercase tracking-wider mb-1"
                    >Key Takeaway</span
                  >
                  <p
                    class="text-xs text-content-muted leading-relaxed font-medium"
                  >
                    {race.forecast.takeaway ||
                      (race.forecast.rationale
                        ? race.forecast.rationale.split(/[.!?]/)[0] + "."
                        : "No summary narrative available.")}
                  </p>
                </div>
              </div>

              <!-- Card Accordion Toggle -->
              <div>
                <div
                  class="flex items-center justify-between border-t border-stroke/10 pt-3"
                >
                  <button
                    type="button"
                    on:click={() => toggleExpand(race.id)}
                    class="text-xs text-blue-600 hover:text-blue-500 dark:text-blue-400 dark:hover:text-blue-300 font-bold flex items-center gap-1 focus:outline-none"
                  >
                    <span
                      class="inline-block transition-transform duration-200"
                      style={isExpanded ? "transform: rotate(180deg);" : ""}
                      >v</span
                    >
                    {isExpanded ? "Hide Analysis" : "Expand Analysis"}
                  </button>

                  <span class="text-[10px] text-content-subtle font-medium">
                    {race.forecast.based_on_poll_count} poll{race.forecast
                      .based_on_poll_count === 1
                      ? ""
                      : "s"} analyzed
                  </span>
                </div>

                <!-- Expandable Drawer Content -->
                {#if isExpanded}
                  <div
                    class="mt-3 pt-3 border-t border-stroke/30 flex flex-col gap-3 text-xs bg-surface-alt/10 rounded-xl p-4 shadow-inner"
                  >
                    <!-- Full Rationale -->
                    <div>
                      <span
                        class="font-bold text-content uppercase tracking-wider text-[9px] block mb-1"
                        >Full Assessment</span
                      >
                      <p
                        class="text-content-muted leading-relaxed font-medium whitespace-pre-wrap"
                      >
                        {race.forecast.rationale}
                      </p>
                    </div>

                    <!-- Key Drivers -->
                    {#if race.forecast.key_reasons && race.forecast.key_reasons.length > 0}
                      <div class="pt-2 border-t border-stroke/20">
                        <span
                          class="font-bold text-content uppercase tracking-wider text-[9px] block mb-1"
                          >Key Drivers</span
                        >
                        <ul
                          class="list-disc list-inside space-y-1 text-content-muted font-medium pl-1"
                        >
                          {#each race.forecast.key_reasons as reason}
                            <li>{reason}</li>
                          {/each}
                        </ul>
                      </div>
                    {/if}

                    <!-- Uncertainty -->
                    {#if race.forecast.uncertainty}
                      <div class="pt-2 border-t border-stroke/20">
                        <span
                          class="font-bold text-content uppercase tracking-wider text-[9px] block mb-1"
                          >Risk Factors & Uncertainty</span
                        >
                        <p
                          class="text-content-muted font-medium leading-relaxed"
                        >
                          {race.forecast.uncertainty}
                        </p>
                      </div>
                    {/if}

                    {#if race.forecast.market_signals && race.forecast.market_signals.length > 0}
                      <div class="pt-2 border-t border-stroke/20">
                        <div
                          class="flex items-center justify-between gap-2 mb-2"
                        >
                          <span
                            class="font-bold text-content uppercase tracking-wider text-[9px] block"
                            >Kalshi Market Signals</span
                          >
                          <span class="text-[9px] text-content-subtle font-bold"
                            >{race.forecast.market_signals.length} market{race
                              .forecast.market_signals.length === 1
                              ? ""
                              : "s"}</span
                          >
                        </div>
                        <div class="grid gap-2">
                          {#each race.forecast.market_signals as signal}
                            <div
                              class="rounded-lg border border-stroke/60 bg-surface px-3 py-2"
                            >
                              <div
                                class="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between"
                              >
                                <div>
                                  <span
                                    class="block text-xs font-bold text-content"
                                    >{marketSignalTarget(signal)}</span
                                  >
                                  <span
                                    class="block text-[10px] text-content-subtle leading-snug"
                                    >{signal.title}</span
                                  >
                                </div>
                                <div
                                  class="flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] text-content-subtle sm:justify-end"
                                >
                                  <span class="font-bold text-content"
                                    >{probabilityOneDecimal(
                                      signal.implied_probability,
                                    )}</span
                                  >
                                  {#if marketSpread(signal)}
                                    <span>{marketSpread(signal)}</span>
                                  {/if}
                                  <span class="capitalize"
                                    >{signal.confidence} confidence</span
                                  >
                                  {#if marketAsOf(signal.as_of)}
                                    <span>As of {marketAsOf(signal.as_of)}</span
                                    >
                                  {/if}
                                  {#if isExternalUrl(signal.url)}
                                    <a
                                      href={signal.url}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      class="font-bold text-blue-600 hover:underline dark:text-blue-400"
                                      >Kalshi</a
                                    >
                                  {/if}
                                </div>
                              </div>
                            </div>
                          {/each}
                        </div>
                      </div>
                    {/if}

                    <!-- Source Links -->
                    {#if race.forecast.source_urls && race.forecast.source_urls.length > 0}
                      <div class="pt-2 border-t border-stroke/20">
                        <span
                          class="font-bold text-content uppercase tracking-wider text-[9px] block mb-1"
                          >Source Documentation</span
                        >
                        <div class="flex flex-wrap gap-1.5">
                          {#each race.forecast.source_urls as url}
                            <a
                              href={url}
                              target="_blank"
                              rel="noopener noreferrer"
                              class="inline-flex items-center text-[10px] text-blue-600 dark:text-blue-400 hover:underline bg-surface border border-stroke px-2 py-0.5 rounded-md truncate max-w-[180px]"
                            >
                              {getHostname(url)} ->
                            </a>
                          {/each}
                        </div>
                      </div>
                    {/if}

                    <!-- Metadata -->
                    <div
                      class="pt-2 border-t border-stroke/20 flex flex-wrap items-center justify-between gap-2 text-[9px] text-content-subtle font-bold"
                    >
                      {#if race.forecast.model}
                        <span>Model: {race.forecast.model}</span>
                      {/if}
                      {#if race.forecast.generated_at}
                        <span
                          >Generated: {new Date(
                            race.forecast.generated_at,
                          ).toLocaleDateString()}</span
                        >
                      {/if}
                    </div>
                  </div>
                {/if}
              </div>
            </article>
          {/each}
        </div>
        {#if sortedRaces.length > visibleRaceCount}
          <div
            class="p-5 text-center border-t border-stroke/40 bg-surface-alt/5"
          >
            <button
              on:click={() => (visibleRaceCount += 12)}
              class="px-5 py-2.5 bg-surface hover:bg-surface-alt border border-stroke/80 rounded-xl text-xs font-bold text-blue-600 dark:text-blue-400 hover:text-blue-500 dark:hover:text-blue-300 transition-all shadow-sm"
            >
              Show More Races ({sortedRaces.length - visibleRaceCount} remaining)
            </button>
          </div>
        {/if}
      {/if}
    </section>

    <!-- Unforecasted Active Races section -->
    {#if filteredMissingRaces.length > 0}
      <section
        class="bg-surface border border-stroke rounded-2xl shadow-sm overflow-hidden opacity-85"
      >
        <div
          class="px-5 py-4 border-b border-stroke/40 flex items-center justify-between bg-surface-alt/10"
        >
          <div>
            <h2 class="text-base font-bold text-content-muted">
              Unforecasted Races ({filteredMissingRaces.length})
            </h2>
            <p class="text-xs text-content-subtle">
              Races currently in the catalog pending forecast modeling
            </p>
          </div>
        </div>
        <div class="overflow-x-auto">
          <table class="min-w-full text-sm">
            <thead
              class="bg-surface-alt/40 border-b border-stroke/40 text-content-subtle text-left"
            >
              <tr>
                <th class="font-bold px-5 py-3">Race Info</th>
                <th class="font-bold px-5 py-3">Status</th>
                <th class="font-bold px-5 py-3">Incumbent Party</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-stroke/40">
              {#each filteredMissingRaces as race}
                {@const stateName = getRaceState(race)}
                {@const fallback = stateName
                  ? INCUMBENT_FALLBACKS[activeTab]?.[stateName]
                  : undefined}
                <tr class="hover:bg-surface-alt/10 transition-colors">
                  <td class="px-5 py-3">
                    <a
                      href={browser ? raceHref(race.id) : undefined}
                      class="font-semibold text-content hover:text-blue-600 dark:hover:text-blue-400"
                    >
                      {race.title ?? race.id}
                    </a>
                  </td>
                  <td class="px-5 py-3 whitespace-nowrap">
                    <span
                      class="inline-flex border border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 text-content-subtle rounded-full px-2 py-0.5 text-xs font-semibold leading-none"
                    >
                      Pending Model Run
                    </span>
                  </td>
                  <td class="px-5 py-3">
                    {#if fallback}
                      <span class={`font-semibold ${partyClass(fallback)}`}>
                        {fallback} (Incumbent Fallback)
                      </span>
                    {:else}
                      <span class="text-content-subtle">Unknown</span>
                    {/if}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </section>
    {/if}

    <!-- Seats Not Up in 2026 section -->
    {#if activeTab !== "house"}
      <section
        class="bg-surface border border-stroke rounded-2xl shadow-sm overflow-hidden mt-6"
      >
        <!-- Toggle header -->
        <button
          on:click={() => (showHoldovers = !showHoldovers)}
          class="w-full px-5 py-4 border-b border-stroke/40 flex items-center justify-between text-left hover:bg-surface-alt/30 transition-colors"
        >
          <div class="flex items-center gap-3">
            <h2 class="text-base font-bold text-content">
              {activeTab === "governors"
                ? "Governor Seats Not Up in 2026"
                : "Senate Seats Not Up in 2026"}
            </h2>
            <span
              class="bg-surface-alt text-content-muted font-bold text-xs px-2.5 py-0.5 rounded-full border border-stroke/60"
            >
              {aggregate.holdovers.length}
              {activeTab === "governors" ? "states" : "seats"}
            </span>
          </div>
          <span class="text-xs text-blue-600 dark:text-blue-400 font-semibold">
            {showHoldovers ? "Hide List ^" : "Show List v"}
          </span>
        </button>

        {#if showHoldovers}
          <div class="p-5 bg-surface-alt/10">
            <p class="text-xs text-content-subtle mb-4">
              These seats are not up for election in 2026 and are factored into
              our control calculations based on current incumbent party
              representation.
            </p>
            <div
              class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3"
            >
              {#each aggregate.holdovers as h}
                <div
                  class="bg-surface border border-stroke/60 rounded-xl px-3 py-2 flex items-center justify-between shadow-sm"
                >
                  <span class="text-xs font-bold text-content truncate pr-1"
                    >{h.state}</span
                  >
                  <span
                    class={`text-[10px] font-extrabold uppercase px-1.5 py-0.5 rounded-md border ${
                      h.party === "Democratic"
                        ? "bg-blue-500/10 text-blue-600 border-blue-500/20 dark:bg-blue-500/20 dark:text-blue-400"
                        : "bg-red-500/10 text-red-600 border-red-500/20 dark:bg-red-500/20 dark:text-red-400"
                    }`}
                  >
                    {h.party === "Democratic" ? "D" : "R"}{h.count > 1
                      ? ` x${h.count}`
                      : ""}
                  </span>
                </div>
              {/each}
            </div>
          </div>
        {/if}
      </section>
    {/if}
  {/if}
</div>

<style lang="postcss">
  .forecast-page button,
  .forecast-page select {
    @apply min-h-11;
  }
</style>
