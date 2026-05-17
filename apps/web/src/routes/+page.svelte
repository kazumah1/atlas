<script lang="ts">
    import { goto } from "$app/navigation";
    import type { PageData } from './$types';

    let { data }: { data: PageData } = $props();

    let query = $state('');
    let date_from = $state('');
    let date_to = $state('');
    let tagsInput = $state('');

    $effect(() => {
        query = data.query;
        date_from = data.date_from ?? '';
        date_to = data.date_to ?? '';
        tagsInput = data.tags.join(', ');
    });

    function buildSearchParams(overrides: Record<string, string | number> = {}): URLSearchParams {
        const params = new URLSearchParams();
        const q = overrides.q !== undefined ? String(overrides.q) : query;
        const df = overrides.date_from !== undefined ? String(overrides.date_from) : date_from;
        const dt = overrides.date_to !== undefined ? String(overrides.date_to) : date_to;
        const tagsStr = overrides.tags !== undefined ? String(overrides.tags) : tagsInput;
        const pg = overrides.page !== undefined ? Number(overrides.page) : data.page;
        
        if (q) params.set('q', q);
        if (df) params.set('date_from', df);
        if (dt) params.set('date_to', dt);
        tagsStr.split(',').map(t => t.trim()).filter(Boolean).forEach(t => params.append('tags', t));
        if (pg > 0) params.set('page', String(pg));
        return params;
    }

    function handleSubmit(e: Event) {
        e.preventDefault();
        goto(`/?${buildSearchParams({ page : 0 })}`);
    }
</script>

<svelte:head>
    <title>Papers Search</title>
</svelte:head>

<form onsubmit={handleSubmit}>
    <input
        type="text"
        bind:value={query}
        placeholder="Search papers..."
        style="width:60%; font-size: 1.1rem; padding:0.4rem;"
    />
    <button type="submit">Search</button>

    <details style="margin-top: 0.5rem;">
        <summary>Filters</summary>
        <div style="margin-top: 0.5rem; display: flex; gap: 1rem; flex-wrap: wrap;">
            <label>
                From
                <input type="date" bind:value={date_from} />
            </label>
            <label>
                To
                <input type="date" bind:value={date_to} />
            </label>
            <label>
                Tags (comma-separated)
                <input type="text" bind:value={tagsInput} placeholder="ml,nlp,vision, etc" />
            </label>
        </div>
    </details>
</form>

{#if data.error}
    <p style="color: red;">Error: {data.error}</p>
{/if}

{#if data.papers.length === 0 && data.query}
    <p>No results for "{data.query}".</p>
{/if}

<div style="margin-top: 1.5rem; display: flex; flex-direction: column; gap: 1rem;">
    {#each data.papers as paper}
        <a href="/papers/{paper.external_id}" style="text-decoration: none; color: inherit;">
            <div style="border: 1px solid #ddd; border-radius: 4px; padding: 1rem;">
                <h3 style="margin: 0 0 0.25rem;">{paper.title}</h3>
                <p style="margin: 0 0 0.25rem; color: #555; font-size: 0.9rem;">
                    {paper.authors.join(', ')} - {new Date(paper.published_at).toLocaleDateString()}
                </p>
                {#if paper.tags && paper.tags.length > 0}
                    <p style="margin: 0 0 0.5rem; font-size; 0.8rem; color: #777;">
                        {paper.tags.join(' | ')}
                    </p>
                {/if}
                {#if paper.abstract}
                    <p style="margin: 0; font-size: 0.9rem; color: #333;">
                        {paper.abstract.slice(0, 300)}{paper.abstract.length > 300 ? '...' : ''}
                    </p>
                {/if}
            </div>
        </a>
    {/each}
</div>

{#if data.papers.length > 0}
    <div style="margin-top: 1rem; display: flex; gap: 1rem;">
        {#if data.page > 0}
            <a href="/?{buildSearchParams({ page: data.page - 1 })}">Prev</a>
        {/if}

        {#if data.papers.length >= data.limit}
            <a href="/?{buildSearchParams({ page: data.page + 1 })}">Next</a>
        {/if}
    </div>
{/if}