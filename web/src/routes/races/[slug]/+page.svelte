<script lang="ts">
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import CandidateCard from '$lib/components/CandidateCard.svelte';
	import type { Race } from '$lib/types';

	let race: Race | null = null;
	let loading = true;
	let error: string | null = null;
	
	$: slug = $page.params.slug;
	
	onMount(async () => {
		try {
			await loadMockData();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load race data';
		} finally {
			loading = false;
		}
	});

	async function loadMockData(): Promise<void> {
		// Mock data for development - replace with actual API call
		race = {
			id: slug,
			title: "Mayor of Example City",
			office: "Mayor",
			jurisdiction: "Example City",
			election_date: "2024-11-05",
			updated_utc: "2024-10-15T10:30:00Z",
			generator: ["GPT-4", "Claude"],
			candidates: [
				{
					name: "Jane Smith",
					party: "Democratic",
					incumbent: true,
					website: "https://janesmith.com",
					social_media: {
						twitter: "https://twitter.com/janesmith",
						facebook: "https://facebook.com/janesmith"
					},
					summary: "Current mayor with 8 years of experience in local government. Focuses on sustainable development and community engagement.",
					top_donors: [
						{
							name: "Local Teachers Union",
							amount: 50000,
							source: "Campaign Finance Report 2024"
						}
					],
					issues: {
						"Healthcare": {
							stance: "Supports expanding community health programs and improving access to mental health services.",
							confidence: "high",
							sources: ["https://janesmith.com/issues/healthcare"]
						},
						"Economy": {
							stance: "Focuses on supporting small businesses and creating green jobs.",
							confidence: "high",
							sources: ["https://janesmith.com/issues/economy"]
						},
						"Climate/Energy": {
							stance: "Advocates for renewable energy transition and carbon neutrality by 2035.",
							confidence: "high",
							sources: ["https://janesmith.com/issues/climate"]
						},
						"Reproductive Rights": {
							stance: "Strongly supports reproductive rights and access to healthcare.",
							confidence: "high",
							sources: ["https://janesmith.com/issues/reproductive"]
						},
						"Immigration": {
							stance: "Supports welcoming policies for immigrants and refugees.",
							confidence: "medium",
							sources: ["https://janesmith.com/issues/immigration"]
						},
						"Guns & Safety": {
							stance: "Supports common-sense gun safety measures.",
							confidence: "medium",
							sources: ["https://janesmith.com/issues/guns"]
						},
						"Foreign Policy": {
							stance: "Focuses on local issues but supports diplomatic solutions.",
							confidence: "low",
							sources: []
						},
						"LGBTQ+ Rights": {
							stance: "Supports LGBTQ+ protections.",
							confidence: "high",
							sources: ["https://janesmith.com/issues/lgbtq"]
						},
						"Education": {
							stance: "Supports increased funding for public schools.",
							confidence: "medium",
							sources: ["https://janesmith.com/issues/education"]
						},
						"Tech & AI": {
							stance: "Promotes responsible AI development.",
							confidence: "low",
							sources: []
						},
						"Election Reform": {
							stance: "Supports ranked-choice voting.",
							confidence: "medium",
							sources: ["https://janesmith.com/issues/election"]
						}
					}
				},
				{
					name: "John Doe",
					party: "Republican",
					incumbent: false,
					website: "https://johndoe.com",
					social_media: {},
					summary: "Local business owner focused on economic development and public safety.",
					top_donors: [],
					issues: {
						"Healthcare": {
							stance: "Opposes universal healthcare.",
							confidence: "medium",
							sources: ["https://johndoe.com/issues/healthcare"]
						},
						"Economy": {
							stance: "Wants to reduce business taxes and regulations.",
							confidence: "high",
							sources: ["https://johndoe.com/issues/economy"]
						},
						"Climate/Energy": {
							stance: "Supports fossil fuel industry.",
							confidence: "medium",
							sources: ["https://johndoe.com/issues/climate"]
						},
						"Reproductive Rights": {
							stance: "Pro-life.",
							confidence: "high",
							sources: ["https://johndoe.com/issues/reproductive"]
						},
						"Immigration": {
							stance: "Supports stricter immigration enforcement.",
							confidence: "high",
							sources: ["https://johndoe.com/issues/immigration"]
						},
						"Guns & Safety": {
							stance: "Supports gun rights.",
							confidence: "high",
							sources: ["https://johndoe.com/issues/guns"]
						},
						"Foreign Policy": {
							stance: "Advocates for strong national defense.",
							confidence: "medium",
							sources: ["https://johndoe.com/issues/foreign"]
						},
						"LGBTQ+ Rights": {
							stance: "Opposes expansion of LGBTQ+ protections.",
							confidence: "low",
							sources: []
						},
						"Education": {
							stance: "Supports school choice.",
							confidence: "medium",
							sources: ["https://johndoe.com/issues/education"]
						},
						"Tech & AI": {
							stance: "Supports deregulation of tech industry.",
							confidence: "low",
							sources: []
						},
						"Election Reform": {
							stance: "Opposes election reforms.",
							confidence: "medium",
							sources: ["https://johndoe.com/issues/election"]
						}
					}
				}
			]
		};
	}
</script>

<svelte:head>
	<title>{race?.title || 'Loading...'} | Smarter.vote</title>
	<meta name="description" content="Compare candidates for {race?.title || 'this election'} on key issues with AI-powered analysis." />
</svelte:head>

<div class="container mx-auto px-4 py-8 max-w-7xl">
	{#if loading}
		<div class="flex items-center justify-center py-20">
			<div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
			<span class="ml-3 text-lg text-gray-600">Loading race data...</span>
		</div>
	{:else if error}
		<div class="bg-red-50 border border-red-200 rounded-lg p-6 text-center">
			<h2 class="text-2xl font-bold text-red-800 mb-2">Error Loading Race</h2>
			<p class="text-red-600">{error}</p>
			<button 
				class="mt-4 bg-red-600 text-white px-4 py-2 rounded hover:bg-red-700"
				on:click={() => window.location.reload()}
			>
				Try Again
			</button>
		</div>
	{:else if race}
		<!-- Race Header -->
		<header class="bg-white rounded-lg shadow-sm p-6 mb-8">
			<h1 class="text-4xl font-bold text-gray-900 mb-4">{race.title}</h1>
			<div class="flex flex-wrap items-center gap-6 text-gray-600">
				<div class="flex items-center gap-2">
					<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
					</svg>
					<span>Election: {new Date(race.election_date).toLocaleDateString()}</span>
				</div>
				<div class="flex items-center gap-2">
					<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
					</svg>
					<span>{race.office} • {race.jurisdiction}</span>
				</div>
				<div class="flex items-center gap-2">
					<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
					</svg>
					<span>Updated: {new Date(race.updated_utc).toLocaleDateString()}</span>
				</div>
			</div>
			<div class="mt-4 flex items-center gap-2 text-sm text-gray-500">
				<span>Analysis by:</span>
				{#each race.generator as model, i}
					<span class="bg-gray-100 px-2 py-1 rounded">{model}</span>
				{/each}
			</div>
		</header>

		<!-- Candidates Section -->
		<section>
			<h2 class="text-2xl font-semibold text-gray-900 mb-6">Candidates</h2>
			<div class="grid gap-8 lg:grid-cols-2">
				{#each race.candidates as candidate}
					<CandidateCard {candidate} />
				{/each}
			</div>
		</section>

		<!-- Data Note -->
		<div class="mt-12 bg-blue-50 border border-blue-200 rounded-lg p-6 text-center">
			<p class="text-blue-800 font-medium mb-2">Data Analysis Information</p>
			<p class="text-blue-700 text-sm">
				Data compiled from public sources and analyzed using AI. Last updated {new Date(race.updated_utc).toLocaleDateString()}.
				Visit candidate websites for the most current information.
			</p>
		</div>
	{/if}
</div>
