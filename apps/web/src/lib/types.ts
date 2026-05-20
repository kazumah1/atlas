export interface Paper {
    id: string;
    external_id: string;
    title: string;
    authors: string[];
    pdf_url: string;
    html_url: string | null;
    abstract: string | null;
    summary: string | null;
    tags: string[] | null;
    published_at: string;
}

export interface SearchResponse {
    results: Paper[];
}

export interface SearchParams {
    query: string;
    date_from?: string;
    date_to?: string;
    tags?: string[];
    page?: number;
    limit?: number;
}