<script lang="ts">
	import { searchPapers } from '$lib/api';

    import type { PageData } from './$types';

    let { data }: { data: PageData } = $props();

    const paper = $derived(data.paper);
    const error = $derived(data.error);
</script>

<svelte:head>
    <title>{paper?.title ?? 'Paper'}</title>
</svelte:head>

<a href="/">Back to search</a>

{#if error}
    <p style="color: red;">Error: {error}</p>
{:else if paper}
    <article>
        <h1>{paper.title}</h1>
        <p style="color: #555;">
            {paper.authors.join(', ')} - {new Date(paper.published_at).toLocaleDateString()}
        </p>

        {#if paper.tags && paper.tags.length > 0}
            <p style="color: #777; font-size: 0.9rem;">Tags: {paper.tags.join(', ')}</p>
        {/if}

        <p>
            <a href={paper.pdf_url} target="_blank" rel="noreferrer">PDF</a>
            {#if paper.html_url}
                &nbsp;|&nbsp;
                <a href={paper.html_url} target="_blank"
                rel="noreferrer">HTML</a>
            {/if}
        </p>

        {#if paper.summary}
            <section>
                <h2>Summary</h2>
                <p>{paper.summary}</p>
            </section>
        {/if}

        {#if paper.abstract}
            <section>
                <h2>Abstract</h2>
                <p>{paper.abstract}</p>
            </section>
        {/if}
    </article>
{:else}
    <p>Paper not found</p>
{/if}