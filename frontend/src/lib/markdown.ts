import { marked } from 'marked'
import hljs from 'highlight.js'
import DOMPurify from 'dompurify'

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

const renderer = new marked.Renderer()

// eslint-disable-next-line @typescript-eslint/no-explicit-any
;(renderer as any).link = function (hrefOrObj: any, title?: string | null, text?: string) {
  if (typeof hrefOrObj === 'object') {
    const tok = hrefOrObj
    return `<a href="${escapeHtml(tok.href)}" target="_blank" rel="noopener noreferrer" title="${escapeHtml(tok.title || '')}">${escapeHtml(tok.text)}</a>`
  }
  return `<a href="${escapeHtml(hrefOrObj)}" target="_blank" rel="noopener noreferrer" title="${escapeHtml(title || '')}">${escapeHtml(text || '')}</a>`
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
;(renderer as any).code = function (codeOrObj: any, language?: string) {
  let codeStr: string, lang: string | undefined
  if (typeof codeOrObj === 'object') {
    lang = codeOrObj.lang
    codeStr = codeOrObj.text
  } else {
    codeStr = codeOrObj
    lang = language
  }
  const highlighted = lang && hljs.getLanguage(lang)
    ? hljs.highlight(codeStr, { language: lang }).value
    : hljs.highlightAuto(codeStr).value
  const escapedLang = lang ? escapeHtml(lang) : ''
  const langLabel = escapedLang
    ? `<span style="position:absolute;top:6px;left:12px;font-size:0.6rem;color:var(--text-muted);font-weight:500;text-transform:uppercase;letter-spacing:0.5px">${escapedLang}</span>`
    : ''
  return `<div class="code-block-wrapper">${langLabel}<button class="code-copy-btn" data-copy-code>COPY</button><pre><code class="hljs${escapedLang ? ' language-' + escapedLang : ''}">${highlighted}</code></pre></div>`
}

marked.setOptions({
  renderer,
  breaks: true,
  gfm: true,
})

// Delegated click handler for copy buttons — no window globals needed
document.addEventListener('click', (e) => {
  const btn = (e.target as HTMLElement).closest('[data-copy-code]') as HTMLButtonElement | null
  if (!btn) return
  const pre = btn.closest('.code-block-wrapper')?.querySelector('pre code')
  if (!pre) return
  navigator.clipboard.writeText(pre.textContent || '').then(() => {
    btn.textContent = 'COPIED'
    btn.classList.add('copied')
    setTimeout(() => { btn.textContent = 'COPY'; btn.classList.remove('copied') }, 1500)
  })
})

export function renderMarkdown(text: string): string {
  if (!text) return ''
  try {
    const raw = marked.parse(text) as string
    return DOMPurify.sanitize(raw, {
      ADD_TAGS: ['button'],
      ADD_ATTR: ['target', 'rel', 'data-copy-code'],
    })
  } catch { return DOMPurify.sanitize(text) }
}
