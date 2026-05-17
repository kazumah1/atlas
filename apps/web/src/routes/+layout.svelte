<script lang="ts">
	let { children } = $props();
</script>

<nav>
	<a href="/">Papers</a>
</nav>

<main>
	{@render children()}
</main>

<style>
	nav {
		padding: 1rem;
		border-bottom: 1px solid #ccc;
	}
	main {
		padding: 1rem 2rem;
		max-width: 900px;
		margin: 0 auto;
	}
</style>