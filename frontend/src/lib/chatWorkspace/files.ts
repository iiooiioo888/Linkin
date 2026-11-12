/**
 * 任務產出檔案清單與路徑樹。
 */
import type { TaskProgress } from '../../types';
import type { WsNode } from './kanban';
import type { WsFile, WsTreeRow } from './types';

function slugFile(title: string): string {
  const s = title
    .trim()
    .replace(/[\\/:*?"<>|]+/g, '')
    .replace(/\s+/g, '_')
    .slice(0, 48);
  return s || 'output';
}

export function wsFiles(task: TaskProgress | null | undefined, nodes: WsNode[]): WsFile[] {
  const files: WsFile[] = [];
  const seen = new Set<string>();
  for (const row of nodes) {
    const listed = row.item.files ?? [];
    if (listed.length) {
      listed.forEach((f, i) => {
        const path = f.path || f.name;
        if (!path || seen.has(path)) return;
        seen.add(path);
        files.push({
          id: `${row.item.id}-${i}`,
          name: f.name || path.split('/').pop() || path,
          path,
          status: f.status === 'added' ? 'added' : f.status === 'deleted' ? 'deleted' : 'modified',
          content: (row.item.output || '').trim(),
          itemId: row.item.id,
          size: f.size,
        });
      });
      continue;
    }
    const output = (row.item.output || '').trim();
    if (!output) continue;
    const name = `${slugFile(row.item.title)}.md`;
    const path = `output/${name}`;
    if (seen.has(path)) continue;
    seen.add(path);
    files.push({
      id: row.item.id,
      name,
      path,
      status: row.status === 'done' ? 'added' : 'modified',
      content: output,
      itemId: row.item.id,
      size: `${output.length}B`,
    });
  }
  const answer = (task?.answer || '').trim();
  if (answer && !files.some((f) => f.content === answer)) {
    files.push({
      id: `${task?.task_id || 'task'}-answer`,
      name: 'deliverable.md',
      path: 'output/deliverable.md',
      status: task?.status === 'completed' ? 'added' : 'modified',
      content: answer,
      size: `${answer.length}B`,
    });
  }
  return files;
}

export function wsTreeRows(files: WsFile[]): WsTreeRow[] {
  const rows: WsTreeRow[] = [];
  const seen = new Set<string>();
  const sorted = [...files].sort((a, b) => a.path.localeCompare(b.path));
  for (const f of sorted) {
    const parts = f.path.split('/').filter(Boolean);
    let acc = '';
    parts.forEach((part, i) => {
      const isFile = i === parts.length - 1;
      acc = acc ? `${acc}/${part}` : part;
      if (!isFile) {
        if (seen.has(acc)) return;
        seen.add(acc);
        rows.push({ kind: 'dir', name: `${part}/`, path: acc, depth: i });
        return;
      }
      rows.push({ kind: 'file', name: part, path: acc, depth: i, file: f });
    });
  }
  return rows;
}
