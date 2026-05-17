import type { PageLoad } from './$types';
import { searchPapers } from '$lib/api';
import type { Paper } from '$lib/types';

export const ssr = false;

const LIMIT = 20;

export const load: PageLoad = async ({ url }) => {
    const query = url.searchParams.get('q') ?? '';
    const date_from = url.searchParams.get('date_from') ?? undefined;
    const date_to = url.searchParams.get('date_to') ?? undefined;

    const tags = url.searchParams.getAll('tags').filter(Boolean);
    const page = Number(url.searchParams.get('page') ?? '0');

    let papers: Paper[] = [];
    let error: string | null = null;

    if (query) {
        try {
            papers = await searchPapers({
                query,
                date_from,
                date_to,
                tags: tags.length > 0 ? tags : undefined,
                page,
                limit: LIMIT,
            });
        } catch (e) {
            error = (e as Error).message;
        }
    }

    return { query, date_from, date_to, tags, page, papers, limit: LIMIT, error };
};

