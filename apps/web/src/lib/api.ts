import type { Paper, SearchParams, SearchResponse } from './types';

const API_BASE = "http://localhost:8000";

export async function searchPapers(params: SearchParams): Promise<Paper[]> {
	const {query, date_from, date_to, tags, page = 0, limit = 20 } = params;

	const url = new URL(`${API_BASE}/search/${encodeURIComponent(query)}`);
	if (date_from) url.searchParams.set('date_from', date_from);
	if (date_to) url.searchParams.set('date_to', date_to);
	if (tags && tags.length > 0) tags.forEach(t => url.searchParams.append('tags', t));
	url.searchParams.set('page', String(page));
	url.searchParams.set('limit', String(limit));

	const res = await fetch(url.toString());
	if (!res.ok) throw new Error(`Search failed: ${res.status}`);
	const data: SearchResponse = await res.json();
	return data.results;
}

/** Default home feed: newest papers by publication date (API may switch to insert-time or personalized later). */
export async function fetchRecentPapers(limit = 20): Promise<Paper[]> {
	const url = new URL(`${API_BASE}/papers/recent`);
	url.searchParams.set('limit', String(limit));
	const res = await fetch(url.toString());
	if (!res.ok) throw new Error(`Recent papers failed: ${res.status}`);
	const data: SearchResponse = await res.json();
	return data.results;
}

export async function getPaper(paperId: string): Promise<Paper> {
	const res = await fetch(`${API_BASE}/papers/${encodeURIComponent(paperId)}`);
	if (!res.ok) throw new Error(`Failed to fetch paper: ${res.status}`);
	return res.json();
}
