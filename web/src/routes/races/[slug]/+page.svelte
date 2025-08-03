<script lang="ts">
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	
	interface Candidate {
		name: string;
		party?: string;
		incumbent: boolean;
		website?: string;
		biography?: string;
		positions: Position[];
	}
	
	interface Position {
		topic: string;
		stance: string;
		summary: string;
		confidence: 'high' | 'medium' | 'low' | 'unknown';
	}
	
	interface Race {
		id: string;
		title: string;
		office: string;
		jurisdiction: string;
		election_date: string;
		candidates: Candidate[];
		description?: string;
		key_issues: string[];
	}
	
	let race: Race | null = null;
	let loading = true;
	let error: string | null = null;
	
	$: slug = $page.params.slug;
	
	onMount(async () => {
		try {
			// TODO: Replace with actual API call
			// const response = await fetch(`/api/races/${slug}`);
			// race = await response.json();
			
			// Mock data for development
			race = {
				id: slug,
				title: "Mayor of Example City",
				office: "Mayor",
				jurisdiction: "Example City",
				election_date: "2024-11-05",
				candidates: [
					{
						name: "Jane Smith",
						party: "Democratic",
						incumbent: true,
						website: "https://janesmith.com",
						biography: "Jane Smith has served as mayor for the past 4 years...",
						positions: [
							{
								topic: "Housing",
								stance: "Pro-affordable housing",
								summary: "Supports increasing affordable housing units by 20%",
								confidence: "high"
							},
							{
								topic: "Transportation",
								stance: "Pro-public transit",
								summary: "Plans to expand bus routes and bike lanes",
								confidence: "medium"
							}
						]
					},
					{
						name: "John Doe",
						party: "Republican",
						incumbent: false,
						website: "https://johndoe.com",
						biography: "John Doe is a local business owner...",
						positions: [
							{
								topic: "Economic Development",
								stance: "Pro-business",
								summary: "Wants to reduce business taxes and regulations",
								confidence: "high"
							},
							{
								topic: "Public Safety",
								stance: "Increase police funding",
								summary: "Proposes hiring 50 additional police officers",
								confidence: "medium"
							}
						]
					}
				],
				description: "The mayoral race for Example City",
				key_issues: ["Housing", "Transportation", "Economic Development", "Public Safety"]
			};
			
			loading = false;
		} catch (e) {
			error = 'Failed to load race information';
			loading = false;
		}
	});
	
	function getConfidenceColor(confidence: string): string {
		switch (confidence) {
			case 'high': return 'text-green-600';
			case 'medium': return 'text-yellow-600';
			case 'low': return 'text-orange-600';
			default: return 'text-gray-600';
		}
	}
</script>

<svelte:head>
	<title>{race ? race.title : 'Loading...'} - SmarterVote</title>
	<meta name="description" content={race?.description || 'Electoral race information'} />
</svelte:head>

<div class="container mx-auto px-4 py-8">
	{#if loading}
		<div class="flex justify-center items-center h-64">
			<div class="animate-spin rounded-full h-32 w-32 border-b-2 border-blue-600"></div>
		</div>
	{:else if error}
		<div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
			<h2 class="font-bold">Error</h2>
			<p>{error}</p>
		</div>
	{:else if race}
		<header class="mb-8">
			<h1 class="text-4xl font-bold text-gray-900 mb-2">{race.title}</h1>
			<div class="text-lg text-gray-600 mb-4">
				<p>{race.office} • {race.jurisdiction}</p>
				<p>Election Date: {new Date(race.election_date).toLocaleDateString()}</p>
			</div>
			{#if race.description}
				<p class="text-gray-700">{race.description}</p>
			{/if}
		</header>

		{#if race.key_issues.length > 0}
			<section class="mb-8">
				<h2 class="text-2xl font-semibold mb-4">Key Issues</h2>
				<div class="flex flex-wrap gap-2">
					{#each race.key_issues as issue}
						<span class="bg-blue-100 text-blue-800 px-3 py-1 rounded-full text-sm">
							{issue}
						</span>
					{/each}
				</div>
			</section>
		{/if}

		<section>
			<h2 class="text-2xl font-semibold mb-6">Candidates</h2>
			<div class="grid gap-8 md:grid-cols-2">
				{#each race.candidates as candidate}
					<div class="bg-white rounded-lg shadow-lg p-6">
						<div class="mb-4">
							<h3 class="text-2xl font-bold text-gray-900">{candidate.name}</h3>
							<div class="flex items-center gap-2 text-sm text-gray-600">
								{#if candidate.party}
									<span class="bg-gray-100 px-2 py-1 rounded">{candidate.party}</span>
								{/if}
								{#if candidate.incumbent}
									<span class="bg-green-100 text-green-800 px-2 py-1 rounded">Incumbent</span>
								{/if}
							</div>
						</div>

						{#if candidate.biography}
							<div class="mb-4">
								<h4 class="font-semibold text-gray-800 mb-2">Biography</h4>
								<p class="text-gray-700">{candidate.biography}</p>
							</div>
						{/if}

						{#if candidate.website}
							<div class="mb-4">
								<a 
									href={candidate.website} 
									target="_blank" 
									rel="noopener noreferrer"
									class="text-blue-600 hover:text-blue-800 underline"
								>
									Official Website
								</a>
							</div>
						{/if}

						{#if candidate.positions.length > 0}
							<div>
								<h4 class="font-semibold text-gray-800 mb-3">Positions</h4>
								<div class="space-y-3">
									{#each candidate.positions as position}
										<div class="border-l-4 border-blue-200 pl-4">
											<div class="flex items-center justify-between mb-1">
												<h5 class="font-medium text-gray-800">{position.topic}</h5>
												<span class="text-xs {getConfidenceColor(position.confidence)} font-medium">
													{position.confidence} confidence
												</span>
											</div>
											<p class="text-sm text-gray-600 mb-1">{position.stance}</p>
											<p class="text-sm text-gray-700">{position.summary}</p>
										</div>
									{/each}
								</div>
							</div>
						{/if}
					</div>
				{/each}
			</div>
		</section>
	{/if}
</div>

<style>
	.container {
		max-width: 1200px;
	}
</style>
