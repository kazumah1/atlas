import renderMathInElement from 'katex/contrib/auto-render';

const options = {
	delimiters: [
		{ left: '$$', right: '$$', display: true },
		{ left: '$', right: '$', display: false },
		{ left: '\\[', right: '\\]', display: true },
		{ left: '\\(', right: '\\)', display: false }
	],
	throwOnError: false,
	strict: 'warn' as const,
	trust: false
};

export function math(node: HTMLElement, value: string | null | undefined) {
	function render(text: string | null | undefined) {
		// Treat paper and LLM content as text before KaTeX transforms math nodes.
		node.textContent = text ?? '';
		renderMathInElement(node, options);
	}

	render(value);

	return { update: render };
}
