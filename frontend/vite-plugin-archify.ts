/**
 * 開發期用 npm 依賴 `archify`（file:../vendor/archify）把 IR 編成 HTML。
 * POST /__archify/render  { ir } → { ok, html, diagram_type, engine }
 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import type { IncomingMessage, ServerResponse } from 'node:http';
import type { Plugin } from 'vite';

type OfficialDoc = {
  diagram_type?: string;
  schema_version?: number;
};

function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on('data', (chunk) => chunks.push(Buffer.from(chunk)));
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    req.on('error', reject);
  });
}

function run(
  command: string,
  args: string[],
  opts: { cwd?: string; input?: string; env?: NodeJS.ProcessEnv; timeoutMs?: number },
): Promise<{ code: number; stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: opts.cwd,
      env: opts.env ?? process.env,
      windowsHide: true,
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    let stdout = '';
    let stderr = '';
    const timer = setTimeout(() => {
      child.kill();
      reject(new Error(`timeout: ${command}`));
    }, opts.timeoutMs ?? 60_000);
    child.stdout?.on('data', (chunk) => {
      stdout += String(chunk);
    });
    child.stderr?.on('data', (chunk) => {
      stderr += String(chunk);
    });
    child.on('error', (err) => {
      clearTimeout(timer);
      reject(err);
    });
    child.on('close', (code) => {
      clearTimeout(timer);
      resolve({ code: code ?? 1, stdout, stderr });
    });
    if (opts.input) child.stdin?.end(opts.input, 'utf8');
    else child.stdin?.end();
  });
}

function sendJson(res: ServerResponse, status: number, payload: unknown) {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.end(JSON.stringify(payload));
}

function archifyBin(repoRoot: string): string {
  const candidates = [
    path.join(repoRoot, 'frontend', 'node_modules', 'archify', 'bin', 'archify.mjs'),
    path.join(repoRoot, 'vendor', 'archify', 'bin', 'archify.mjs'),
  ];
  const found = candidates.find((row) => fs.existsSync(row));
  if (!found) {
    throw new Error('找不到 archify CLI。請在 frontend 執行 npm install。');
  }
  return found;
}

function archifyRoot(binPath: string): string {
  return path.dirname(path.dirname(binPath));
}

function pythonBin(): string {
  return process.env.ARCHIFY_PYTHON || process.env.PYTHON || 'python';
}

async function compileIr(repoRoot: string, ir: unknown): Promise<OfficialDoc> {
  const script = path.join(repoRoot, 'backend', 'scripts', 'archify_compile_ir.py');
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'archify-ir-'));
  const src = path.join(tmp, 'ir.json');
  try {
    fs.writeFileSync(src, JSON.stringify(ir), 'utf8');
    const result = await run(pythonBin(), [script, src], {
      cwd: repoRoot,
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
      timeoutMs: 20_000,
    });
    if (result.code !== 0) {
      throw new Error((result.stderr || result.stdout || 'compile_ir 失敗').slice(-2000));
    }
    return JSON.parse(result.stdout) as OfficialDoc;
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
}

function injectIframeCss(html: string): string {
  if (html.includes('id="linkin-archify-iframe"')) return html;
  const extra =
    '<style id="linkin-archify-iframe">' +
    'html,body{min-height:100%;height:auto;}' +
    '.diagram-container{max-width:100%;overflow:auto!important;}' +
    '.diagram-container svg,svg[viewBox]{display:block;width:100%!important;' +
    'max-width:100%;height:auto!important;min-height:240px;}' +
    '</style>';
  return html.replace('</head>', `${extra}</head>`);
}

async function renderWithArchifyCli(repoRoot: string, document: OfficialDoc): Promise<string> {
  const diagramType =
    document.diagram_type === 'data-flow' ? 'dataflow' : String(document.diagram_type || 'architecture');
  const bin = archifyBin(repoRoot);
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'archify-'));
  const src = path.join(tmp, `${diagramType}.json`);
  const dst = path.join(tmp, `${diagramType}.html`);
  try {
    fs.writeFileSync(src, JSON.stringify(document, null, 2), 'utf8');
    const result = await run(process.execPath, [bin, 'render', diagramType, src, dst, '--quality', 'standard'], {
      cwd: archifyRoot(bin),
      env: {
        ...process.env,
        ARCHIFY_QUALITY_PROFILE: 'standard',
        ARCHIFY_UPDATE_CHECK_DISABLED: '1',
      },
      timeoutMs: 45_000,
    });
    if (result.code !== 0 || !fs.existsSync(dst)) {
      throw new Error((result.stderr || result.stdout || 'archify render 失敗').slice(-2000));
    }
    return injectIframeCss(fs.readFileSync(dst, 'utf8'));
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
}

async function handleRender(repoRoot: string, req: IncomingMessage, res: ServerResponse) {
  const body = JSON.parse((await readBody(req)) || '{}') as { ir?: unknown; document?: OfficialDoc };
  const raw = body.document ?? body.ir;
  if (!raw || typeof raw !== 'object') {
    sendJson(res, 400, { ok: false, error: '請傳 ir 或 document' });
    return;
  }
  const official =
    typeof (raw as OfficialDoc).schema_version === 'number' && (raw as OfficialDoc).diagram_type
      ? (raw as OfficialDoc)
      : await compileIr(repoRoot, raw);
  const html = await renderWithArchifyCli(repoRoot, official);
  sendJson(res, 200, {
    ok: true,
    html,
    diagram_type: official.diagram_type,
    engine: 'archify',
    source: 'https://github.com/tt-a1i/archify',
  });
}

export function archifyRenderPlugin(repoRoot: string): Plugin {
  const mount = (server: { middlewares: { use: (fn: (req: IncomingMessage, res: ServerResponse, next: () => void) => void) => void } }) => {
    server.middlewares.use((req, res, next) => {
      const url = req.url?.split('?')[0];
      if (url !== '/__archify/render' || req.method !== 'POST') {
        next();
        return;
      }
      void handleRender(repoRoot, req, res).catch((err: unknown) => {
        sendJson(res, 502, { ok: false, error: err instanceof Error ? err.message : String(err) });
      });
    });
  };

  return {
    name: 'archify-render',
    configureServer: mount,
    configurePreviewServer: mount,
  };
}
