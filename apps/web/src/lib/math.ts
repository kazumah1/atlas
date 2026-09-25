type AutoRenderOptions = {
	delimiters: Array<{ left: string; right: string; display: boolean }>;
	throwOnError: boolean;
	strict: 'warn';
	trust: boolean;
};

declare global {
	interface Window {
		renderMathInElement?: (node: HTMLElement, options: AutoRenderOptions) => void;
	}
}

const options: AutoRenderOptions = {
	delimiters: [
		{ left: '$$', right: '$$', display: true },
		{ left: '$', right: '$', display: false },
		{ left: '\\[', right: '\\]', display: true },
		{ left: '\\(', right: '\\)', display: false }
	],
	throwOnError: false,
	strict: 'warn',
	trust: false
};

export function math(node: HTMLElement, value: string | null | undefined) {
	let currentValue = value;
	let destroyed = false;

	function render(text: string | null | undefined) {
		currentValue = text;
		// Treat paper and LLM content as text before KaTeX transforms math nodes.
		node.textContent = text ?? '';
		window.renderMathInElement?.(node, options);
	}

	function renderWhenScriptsAreReady() {
		if (!destroyed) render(currentValue);
	}

	render(value);
	if (!window.renderMathInElement) {
		window.addEventListener('load', renderWhenScriptsAreReady, { once: true });
	}

	return {
		update: render,
		destroy() {
			destroyed = true;
			window.removeEventListener('load', renderWhenScriptsAreReady);
		}
	};
}
