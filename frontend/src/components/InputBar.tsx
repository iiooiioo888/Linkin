/** 輸入列：極簡 composer，模式收在選單內；支援 /context 斜線命令。 */
import { useMemo, useRef, useState } from 'react';
import type { FormEvent, KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { COMPANY_TEMPLATES } from '../types';
import type { RoutingPreviewSnapshot } from '../lib/routingPreview';
import type { CompanyTemplate, TaskOptions } from '../types';
import { openChatContextDetail, openContextModal } from '../lib/contextUi';
import { useRoutingPreview } from '../hooks/useRoutingPreview';
import { RoutingPreviewChips } from './ui/monitor';

export interface SendOptions {
  executionStrategy: 'auto' | 'simple' | 'company';
  companyTemplate: CompanyTemplate;
  taskOptions?: TaskOptions;
  /** 已通過需求審計官，跳過前置閘門 */
  skipGrill?: boolean;
  /** 發送當下路由預覽快照（含 query／mode／template；不一致時 App 會重取） */
  routingPreviewSnapshot?: RoutingPreviewSnapshot | null;
}

interface InputBarProps {
  disabled: boolean;
  onSend: (text: string, options: SendOptions) => void;
  compact?: boolean;
  /**
   * `/context`｜`/context peek`：由對話頁注入，必須綁定**當前對話** taskId。
   * 不得在此處自行 openContextModal() 以免回落其他會話軌跡。
   */
  onContextCommand?: (mode: 'detail' | 'peek') => void;
}

/** 發送由後端護欄結算；輸入列不顯示預估用量。 */

const STRATEGIES: { key: 'auto' | 'simple' | 'company'; label: string }[] = [
  { key: 'auto', label: '自動' },
  { key: 'simple', label: '簡單' },
  { key: 'company', label: '公司' },
];

const SLASH_COMMANDS = [
  {
    cmd: '/context',
    label: '查看上下文',
    hint: '在對話底部看這次用了哪些資料',
  },
  {
    cmd: '/context peek',
    label: '預覽上下文',
    hint: '彈出預覽，不離開目前對話',
  },
] as const;

export default function InputBar({
  disabled,
  onSend,
  compact = false,
  onContextCommand,
}: InputBarProps) {
  const { t } = useTranslation();
  const [text, setText] = useState('');
  const [executionStrategy, setExecutionStrategy] = useState<'auto' | 'simple' | 'company'>('auto');
  const [companyTemplate, setCompanyTemplate] = useState<CompanyTemplate>('quick_task');
  const [showMenu, setShowMenu] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [budgetLimit, setBudgetLimit] = useState('');
  const [maxParallel, setMaxParallel] = useState('');
  const [maxIterations, setMaxIterations] = useState('');
  const [maxReviewRounds, setMaxReviewRounds] = useState('');
  const [passThreshold, setPassThreshold] = useState('');
  const [slashIndex, setSlashIndex] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const strategyLabel = STRATEGIES.find((s) => s.key === executionStrategy)?.label ?? '自動';
  const { snapshot: routingPreviewSnapshot } = useRoutingPreview(
    text,
    executionStrategy,
    companyTemplate,
  );
  const routingPreview = routingPreviewSnapshot?.preview ?? null;

  const slashMatches = useMemo(() => {
    const trimmed = text.trim();
    if (!trimmed.startsWith('/')) return [];
    const q = trimmed.toLowerCase();
    // 允許「/context peek」中間空白；選單在尚未輸入空格時也顯示 peek
    return SLASH_COMMANDS.filter((c) => {
      if (c.cmd === '/context peek') {
        return q === '/' || q.startsWith('/context') || '/context peek'.startsWith(q);
      }
      return c.cmd.startsWith(q) || q === '/';
    });
  }, [text]);

  const autoResize = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
  };

  const clearComposer = () => {
    setText('');
    setShowMenu(false);
    requestAnimationFrame(() => {
      if (textareaRef.current) textareaRef.current.style.height = 'auto';
    });
  };

  const runContextCommand = (mode: 'detail' | 'peek' = 'detail') => {
    if (onContextCommand) {
      onContextCommand(mode);
    } else if (mode === 'peek') {
      // 非對話頁兜底：不帶 taskId → ContextModal 顯示空態，禁止抓全域最新軌跡
      openContextModal(null);
    } else {
      openChatContextDetail(null);
    }
    clearComposer();
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    // /context [peek]：開啟可視化，不送入對話（對齊 dsh-context）
    if (/^\/context(?:\s+peek)?$/i.test(trimmed)) {
      runContextCommand(/\bpeek\b/i.test(trimmed) ? 'peek' : 'detail');
      return;
    }
    const taskOptions: TaskOptions = {};
    if (budgetLimit) taskOptions.budget_limit = parseFloat(budgetLimit);
    if (maxParallel) taskOptions.max_parallel = parseInt(maxParallel, 10);
    if (maxIterations) taskOptions.max_iterations = parseInt(maxIterations, 10);
    if (maxReviewRounds) taskOptions.max_review_rounds = parseInt(maxReviewRounds, 10);
    if (passThreshold) taskOptions.pass_threshold = parseFloat(passThreshold);
    onSend(trimmed, {
      executionStrategy,
      companyTemplate,
      taskOptions,
      routingPreviewSnapshot,
    });
    setText('');
    setShowMenu(false);
    requestAnimationFrame(() => {
      if (textareaRef.current) textareaRef.current.style.height = 'auto';
    });
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (slashMatches.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSlashIndex((i) => (i + 1) % slashMatches.length);
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSlashIndex((i) => (i - 1 + slashMatches.length) % slashMatches.length);
        return;
      }
      if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey && text.trim().startsWith('/'))) {
        const pick = slashMatches[slashIndex] ?? slashMatches[0];
        if (pick?.cmd === '/context' || pick?.cmd === '/context peek') {
          e.preventDefault();
          runContextCommand(pick.cmd === '/context peek' ? 'peek' : 'detail');
          return;
        }
      }
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <div className={`apple-input-bar shrink-0 ${compact ? '!px-0 !py-0 !border-0' : ''}`}>
      <div className={`relative mx-auto w-full ${compact ? '' : 'max-w-3xl'}`}>
        {showAdvanced && (
          <div className="mb-2 rounded-xl border border-white/[0.06] bg-[var(--console-card)] p-3">
            <p className="mb-2 text-[10px] font-medium text-[var(--console-sub)]">進階</p>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {[
                { label: '花費上限', value: budgetLimit, set: setBudgetLimit },
                { label: '同時幾路', value: maxParallel, set: setMaxParallel },
                { label: '重試次數', value: maxIterations, set: setMaxIterations },
                { label: '審查次數', value: maxReviewRounds, set: setMaxReviewRounds },
                { label: '通過分數', value: passThreshold, set: setPassThreshold },
              ].map((f) => (
                <div key={f.label}>
                  <label className="mb-0.5 block text-[10px] text-[var(--console-sub)]">{f.label}</label>
                  <input
                    type="number"
                    value={f.value}
                    onChange={(e) => f.set(e.target.value)}
                    placeholder="預設"
                    disabled={disabled}
                    className="apple-field"
                  />
                </div>
              ))}
            </div>
          </div>
        )}

        {slashMatches.length > 0 && (
          <div className="absolute bottom-full left-0 z-20 mb-2 w-72 overflow-hidden rounded-xl border border-white/[0.08] bg-[var(--console-card)] shadow-xl">
            <p className="px-3 py-1.5 text-[10px] text-[var(--console-sub)]">斜線命令</p>
            {slashMatches.map((c, i) => (
              <button
                key={c.cmd}
                type="button"
                className={`flex w-full flex-col gap-0.5 px-3 py-2 text-left ${
                  i === slashIndex ? 'bg-[color-mix(in_srgb,var(--console-accent)_15%,transparent)]' : 'hover:bg-white/[0.04]'
                }`}
                onMouseEnter={() => setSlashIndex(i)}
                onClick={() => {
                  if (c.cmd === '/context') runContextCommand('detail');
                  else if (c.cmd === '/context peek') runContextCommand('peek');
                }}
              >
                <span className="font-mono text-[12px] text-[var(--console-accent)]">{c.cmd}</span>
                <span className="text-[11px] text-[var(--console-ink)]">{c.label}</span>
                <span className="text-[10px] text-[var(--console-sub)]">{c.hint}</span>
              </button>
            ))}
          </div>
        )}

        {showMenu && (
          <div className="absolute bottom-full left-0 z-10 mb-2 w-52 rounded-xl border border-white/[0.08] bg-[var(--console-card)] p-1.5 shadow-xl">
            <p className="px-2 py-1 text-[10px] text-[var(--console-sub)]">執行模式</p>
            {STRATEGIES.map((s) => (
              <button
                key={s.key}
                type="button"
                onClick={() => setExecutionStrategy(s.key)}
                className={`flex w-full rounded-lg px-2.5 py-1.5 text-left text-[12px] ${
                  executionStrategy === s.key
                    ? 'bg-[color-mix(in_srgb,var(--console-accent)_15%,transparent)] text-[#64B5FF]'
                    : 'text-[var(--console-sub)] hover:bg-white/[0.04]'
                }`}
              >
                {s.label}
              </button>
            ))}
            {executionStrategy === 'company' && (
              <select
                value={companyTemplate}
                onChange={(e) => setCompanyTemplate(e.target.value as CompanyTemplate)}
                disabled={disabled}
                className="mt-1 w-full apple-select"
              >
                {COMPANY_TEMPLATES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            )}
            <button
              type="button"
              onClick={() => {
                setShowAdvanced((v) => !v);
                setShowMenu(false);
              }}
              className="mt-1 w-full rounded-lg px-2.5 py-1.5 text-left text-[12px] text-[var(--console-sub)] hover:bg-white/[0.04]"
            >
              進階選項…
            </button>
            <button
              type="button"
              className="mt-1 w-full rounded-lg px-2.5 py-1.5 text-left text-[12px] text-[var(--console-sub)] hover:bg-white/[0.04] hover:text-[var(--console-accent)]"
              onClick={() => {
                setShowMenu(false);
                runContextCommand('detail');
              }}
            >
              查看上下文
            </button>
            <button
              type="button"
              className="mt-1 w-full rounded-lg px-2.5 py-1.5 text-left text-[12px] text-[var(--console-sub)] hover:bg-white/[0.04] hover:text-[var(--console-accent)]"
              onClick={() => {
                setShowMenu(false);
                runContextCommand('peek');
              }}
            >
              預覽上下文
            </button>
            <a
              href="#/monitor/integrations"
              className="mt-1 block w-full rounded-lg px-2.5 py-1.5 text-left text-[12px] text-[var(--console-sub)] hover:bg-white/[0.04] hover:text-[var(--console-accent)]"
              onClick={() => setShowMenu(false)}
            >
              外部工具
            </a>
          </div>
        )}

        <form onSubmit={handleSubmit} className="apple-composer">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setSlashIndex(0);
              autoResize();
            }}
            onKeyDown={handleKeyDown}
            placeholder={compact ? '輸入訊息給 Agent… 或 /context' : '輸入問題… 或 /context'}
            rows={1}
            disabled={disabled}
            className="apple-composer__field"
          />
          <div className="apple-composer__toolbar">
            <button
              type="button"
              onClick={() => setShowMenu((v) => !v)}
              disabled={disabled}
              className={`shrink-0 rounded-lg px-2 py-1 text-[11px] text-[var(--console-faint)] hover:bg-white/[0.04] hover:text-[var(--console-ink)] ${
                showMenu ? 'bg-white/[0.06] text-[var(--console-ink)]' : ''
              }`}
            >
              {strategyLabel}
            </button>

            {routingPreview && (
              <RoutingPreviewChips preview={routingPreview} compact className="min-w-0 flex-1 sm:flex-none" />
            )}

            <button
              type="submit"
              disabled={disabled || !text.trim()}
              className="apple-send-btn ml-auto"
              aria-label={t('chat.send')}
            >
              {disabled ? (
                <span className="apple-send-btn__spinner" />
              ) : (
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden>
                  <path d="M2.5 8L13.5 3L9 8L13.5 13L2.5 8Z" fill="currentColor" />
                </svg>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
