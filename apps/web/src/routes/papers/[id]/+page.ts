import type { PageLoad } from './$types';
import { getPaper } from '$lib/api';
import type { Paper } from '$lib/types';

export const ssr = false;

export const load: PageLoad = async ({ params }) => {
    let paper: Paper | null = null;
    let error: string | null = null;

    try {
        paper = await getPaper(params.id);
    } catch (e) {
        error = (e as Error).message;
    }

    return { paper, error };
};