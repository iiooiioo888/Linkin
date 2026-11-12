/**
 * 對話工作台型別：思考步驟、檔案樹、問題、終端與程式碼 token。
 */
export interface WsThinkingStep {
  id: string;
  ts: number;
  title: string;
  text: string;
  kind: 'success' | 'process' | 'warning';
  code?: string;
  tokens?: number;
}

export interface WsFile {
  id: string;
  name: string;
  path: string;
  status: 'added' | 'modified' | 'deleted';
  content: string;
  itemId?: string;
  size?: string;
  time?: string;
}

export interface WsTreeRow {
  kind: 'dir' | 'file';
  name: string;
  path: string;
  depth: number;
  file?: WsFile;
}

export interface WsProblem {
  id: string;
  title: string;
  detail: string;
  tone: 'warn' | 'err';
  loc?: string;
}

export interface WsTermLine {
  kind: 'info' | 'warn' | 'err' | 'cmd' | 'out';
  text: string;
}

export interface WsCodeTok {
  t: string;
  k: 'plain' | 'keyword' | 'function' | 'string' | 'comment' | 'variable' | 'number';
}
