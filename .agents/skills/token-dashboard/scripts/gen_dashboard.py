# -*- coding: utf-8 -*-
"""WorkBuddy Token 消耗看板构建脚本

扫描 ~/.workbuddy/projects/<工作空间>/*.jsonl，抽取请求级 usage 数据，
生成单文件自包含看板 token-dashboard.html（离线可看）。

跨平台：Windows / macOS / Linux 通用，仅依赖 Python 标准库（3.8+）。

用法：
    python gen_dashboard.py                    # 输出到当前目录 token-dashboard.html
    python gen_dashboard.py --out 看板.html     # 自定义输出路径
    python gen_dashboard.py --projects <目录>   # 自定义会话日志目录
"""
import argparse
import datetime
import glob
import json
import os
import sys
from pathlib import Path

from dashboard_render import render_html

# Windows 控制台 GBK 环境下防止中文 print 报错
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_ap = argparse.ArgumentParser(description="WorkBuddy Token 消耗看板生成器")
_ap.add_argument("--projects", default=os.path.join(os.path.expanduser("~"), ".workbuddy", "projects"),
                 help="WorkBuddy 会话日志目录（默认 ~/.workbuddy/projects）")
_ap.add_argument("--out", default="token-dashboard.html", help="输出 HTML 路径（默认当前目录 token-dashboard.html）")
_ap.add_argument("--source", choices=["workbuddy", "linkin"], default="workbuddy",
                 help="資料來源：workbuddy（本機日誌）或 linkin（計費庫）")
_ap.add_argument("--user", default="", help="Linkin 帳號 user_id（--source linkin 時）")
_ap.add_argument("--days", type=int, default=90, help="Linkin 回溯天數（--source linkin）")
_args = _ap.parse_args()
OUT = _args.out

if _args.source == "linkin":
    try:
        from backend.billing.token_dashboard.adapter import collect_linkin_usage
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        from backend.billing.token_dashboard.adapter import collect_linkin_usage
    data = collect_linkin_usage(_args.user or None, days=_args.days)
    html = render_html(data)
    open(OUT, "w", encoding="utf-8").write(html)
    print("written:", OUT, f"({os.path.getsize(OUT)/1e6:.1f} MB)")
    print(
        "sessions:",
        len(data.get("sess", [])),
        "| models:",
        len(data.get("models", [])),
        "| workspaces:",
        len(data.get("ws", [])),
    )
    sys.exit(0)

PROJECTS = _args.projects
def parse_ts(v):
    if isinstance(v, (int, float)):
        if v > 1e12: return v / 1000.0
        if v > 1e9: return float(v)
    if isinstance(v, str):
        s = v.strip()
        for fmt_ in ('%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%SZ',
                     '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f'):
            try:
                import calendar
                return calendar.timegm(datetime.datetime.strptime(s, fmt_).timetuple())
            except Exception:
                pass
        try: return float(s) / 1000.0
        except Exception: return None
    return None

def grab(o):
    pd = o.get('providerData')
    if not isinstance(pd, dict): return None
    ru = pd.get('rawUsage') or {}; u = pd.get('usage') or {}
    tt = ru.get('total_tokens') or u.get('totalTokens')
    if not tt: return None
    model = pd.get('model') or pd.get('requestModelId') or pd.get('requestModelName') or 'unknown'
    ptd = ru.get('prompt_tokens_details') or {}
    ch = ru.get('prompt_cache_hit_tokens')
    if ch is None: ch = ptd.get('cached_tokens') or 0  # 兜底：DeepSeek 风格顶层字段 → OpenAI 风格嵌套字段（claude/qwen/glm）
    cw = ptd.get('cached_creation_tokens') or ptd.get('cache_write_tokens') or 0  # 缓存写入（Claude 按 1.25× 输入价计）
    return dict(tt=int(tt), it=int(ru.get('prompt_tokens') or u.get('inputTokens') or 0),
                ot=int(ru.get('completion_tokens') or u.get('outputTokens') or 0),
                ch=int(ch or 0), cw=int(cw or 0), model=model)

def session_title(o, fallback):
    """取首条非 system-reminder 的用户消息前 42 字作为任务标题；跳过 < 开头的内部标签消息"""
    if o.get('role') != 'user': return None
    c = o.get('content')
    if isinstance(c, str):
        t = ' '.join(c.split())
        if t and not t.startswith('<'):
            return t[:42]
        return None
    if not isinstance(c, list): return None
    for seg in c:
        if isinstance(seg, dict) and seg.get('type') == 'input_text':
            t = (seg.get('text') or '').strip()
            if not t: continue
            if t.startswith('<'): return None
            t = ' '.join(t.split())
            return t[:42]
        if isinstance(seg, dict) and seg.get('type') == 'text':
            t = (seg.get('text') or '').strip()
            if not t: continue
            if t.startswith('<'): return None
            t = ' '.join(t.split())
            return t[:42]
    return None

MODEL_MERGE={'glm-5.2-x':'glm-5.2'}

def short_ws(name):
    """工作空间目录名是路径 slug（如 c-Users-foo-WorkBuddy-2026-08-01-10-00-00），
    取 WorkBuddy 之后的部分作为短名；非 WorkBuddy 目录（如桌面工作区）原样返回"""
    i = name.rfind('-WorkBuddy-')
    if i >= 0 and name[i + 11:]:
        return name[i + 11:]
    return name

now = datetime.datetime.now()
gen_ms = int(now.timestamp() * 1000)

ws_names = {}      # folder -> short
ws_idx = {}        # folder -> index
models = [] ; model_idx = {}
sessions = {}      # sid -> dict
files = glob.glob(os.path.join(PROJECTS, '**', '*.jsonl'), recursive=True)
for fp in files:
    rel = os.path.relpath(fp, PROJECTS)
    parts = rel.split(os.sep)
    folder = parts[0]
    # 二级文件 = 会话文件；三级及更深（subagents/agent-*.jsonl）归属父会话
    sid = os.path.splitext(parts[1])[0] if len(parts) == 2 else parts[1]
    if folder not in ws_idx:
        ws_names[folder] = short_ws(folder)
        ws_idx[folder] = len(ws_idx)
    recs = []
    title = None
    with open(fp, encoding='utf-8', errors='ignore') as fh:
        for line in fh:
            try: o = json.loads(line)
            except Exception: continue
            if not isinstance(o, dict): continue
            sid_r = o.get('sessionId')
            if sid_r and len(parts) == 2: sid = sid_r  # 子代理文件保持归属父会话
            if title is None:
                t = session_title(o, sid)
                if t: title = t
            r = grab(o)
            if not r: continue
            r['model'] = MODEL_MERGE.get(r['model'], r['model'])
            ts = parse_ts(o.get('timestamp'))
            if not ts: continue
            if r['model'] not in model_idx:
                model_idx[r['model']] = len(models); models.append(r['model'])
            recs.append((int(ts // 60), model_idx[r['model']], r['tt'], r['it'], r['ot'], r['ch'], r['cw']))
    if not recs: continue
    recs.sort(key=lambda x: x[0])
    d = sessions.setdefault(sid, {'w': ws_idx[folder], 'id': sid, 't': title, 'r': []})
    d['r'].extend(recs)

sess_list = []
for sid, d in sessions.items():
    if not d['r']: continue
    sess_list.append({'w': d['w'], 'id': sid[:8], 't': d['t'] or '(无标题会话)', 'st': d['r'][0][0], 'r': d['r']})
sess_list.sort(key=lambda s: s['st'])

DATA = {'genMs': gen_ms, 'gen': now.strftime('%Y-%m-%d %H:%M'), 'ws': list(ws_names.values()), 'models': models, 'sess': sess_list}
html = render_html(DATA)
open(OUT, 'w', encoding='utf-8').write(html)
print('written:', OUT, f'({os.path.getsize(OUT)/1e6:.1f} MB)')
print('sessions:', len(sess_list), '| models:', len(models), '| workspaces:', len(ws_names))
