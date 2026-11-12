/**
 * 程式碼語言與 token 著色。
 */
import type { WsCodeTok } from './types';

const KEYWORDS = new Set([
  'export',
  'import',
  'from',
  'interface',
  'type',
  'class',
  'function',
  'const',
  'let',
  'return',
  'if',
  'else',
  'async',
  'await',
  'def',
  'class',
  'string',
  'number',
  'boolean',
  'true',
  'false',
  'null',
  'undefined',
]);

export function langOf(path: string): string {
  const ext = path.split('.').pop()?.toLowerCase() || '';
  if (ext === 'ts' || ext === 'tsx') return 'TypeScript';
  if (ext === 'js' || ext === 'jsx') return 'JavaScript';
  if (ext === 'py') return 'Python';
  if (ext === 'json') return 'JSON';
  if (ext === 'md') return 'Markdown';
  if (ext === 'css') return 'CSS';
  if (ext === 'html') return 'HTML';
  return ext.toUpperCase() || 'Text';
}

export function tokenizeCode(line: string): WsCodeTok[] {
  if (!line) return [{ t: ' ', k: 'plain' }];
  const out: WsCodeTok[] = [];
  const push = (t: string, k: WsCodeTok['k']) => {
    if (t) out.push({ t, k });
  };
  let rest = line;
  while (rest.length) {
    const comment = rest.match(/^(\/\/.*|#(?!\{).*)$/);
    if (comment) {
      push(comment[1], 'comment');
      break;
    }
    const str = rest.match(/^(['"`])(?:\\.|(?!\1).)*\1/);
    if (str) {
      push(str[0], 'string');
      rest = rest.slice(str[0].length);
      continue;
    }
    const num = rest.match(/^\d+(?:\.\d+)?/);
    if (num) {
      push(num[0], 'number');
      rest = rest.slice(num[0].length);
      continue;
    }
    const word = rest.match(/^[A-Za-z_][\w]*/);
    if (word) {
      const w = word[0];
      const next = rest.slice(w.length);
      if (KEYWORDS.has(w)) push(w, 'keyword');
      else if (next.startsWith('(')) push(w, 'function');
      else if (/^[A-Z]/.test(w)) push(w, 'variable');
      else push(w, 'plain');
      rest = next;
      continue;
    }
    push(rest[0], 'plain');
    rest = rest.slice(1);
  }
  return out.length ? out : [{ t: line, k: 'plain' }];
}
