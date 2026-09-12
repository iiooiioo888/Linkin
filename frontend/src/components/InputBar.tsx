/** 輸入列：極簡 composer，模式收在選單內；支援 /context 斜線命令。 */
import { useMemo, useRef, useState } from 'react';
import type { FormEvent, KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { COMPANY_TEMPLATES } from '../types';
import type { CompanyTemplate, TaskOptions } from '../types';
import { openChatContextDetail, openContextModal } from '../lib/contextUi';
import { useWallet } from '../hooks/useWallet';
import InputCreditBar, { estimateCredits, MIN_SEND_CREDITS } from './chat/InputCreditBar';

export interface SendOptions {
  executionStrategy: 'auto' | 'simple' | 'company';
  companyTemplate: CompanyTemplate;
  taskOptions?: TaskOptions;
  /** 已通過需求審計官，跳過前置閘門 */
  skipGrill?: boolean;
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
  onOpenBilling?: () => void;
  liveSpent?: number | null;
}

const STRATEGIES: { key: 'auto' | 'simple' | 'company'; label: string }[] = [
  { key: 'auto', label: '自動' },
  { key: 'simple', label: '簡單' },
  { key: 'company', label: '公司' },
];

const SLASH_COMMANDS = [
  {
    cmd: '/context',
    label: 'Context 詳細區',
    hint: '對話底部：組成／瀏覽器／事件（dsh-context）',
  },
  {
    cmd: '/context peek',
    label: 'Context Peek',
    hint: '浮動預覽模態（不離開當前頁）',
  },
] as const;

export default function InputBar({
  disabled,
  onSend,
  compact = false,
  onContextCommand,
  onOpenBilling,
  liveSpent,
}: InputBarProps) {
  const { t } = useTranslation();
  const { account } = useWallet(12000);
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

  const balance = account?.balance_credits ?? null;
  const estCost = estimateCredits(text, executionStrategy);
  const insufficient = balance !== null && balance < Math.max(MIN_SEND_CREDITS, estCost);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || disabled || insufficient) return;
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
    onSend(trimmed, { executionStrategy, companyTemplate, taskOptions });
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
          <div className="mb-2 rounded-xl border border-white/[0.06] bg-[#1C1C1E] p-3">
            <p className="mb-2 text-[10px] font-medium text-[#636366]">進階</p>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {[
                { label: '預算 ($)', value: budgetLimit, set: setBudgetLimit },
                { label: '並行', value: maxParallel, set: setMaxParallel },
                { label: '迭代', value: maxIterations, set: setMaxIterations },
                { label: '審查', value: maxReviewRounds, set: setMaxReviewRounds },
                { label: '門檻', value: passThreshold, set: setPassThreshold },
              ].map((f) => (
                <div key={f.label}>
                  <label className="mb-0.5 block text-[10px] text-[#636366]">{f.label}</label>
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
          <div className="absolute bottom-full left-0 z-20 mb-2 w-72 overflow-hidden rounded-xl border border-white/[0.08] bg-[#1C1C1E] shadow-xl">
            <p className="px-3 py-1.5 text-[10px] text-[#636366]">斜線命令</p>
            {slashMatches.map((c, i) => (
              <button
                key={c.cmd}
                type="button"
                className={`flex w-full flex-col gap-0.5 px-3 py-2 text-left ${
                  i === slashIndex ? 'bg-[#0A84FF]/15' : 'hover:bg-white/[0.04]'
                }`}
                onMouseEnter={() => setSlashIndex(i)}
                onClick={() => {
                  if (c.cmd === '/context') runContextCommand('detail');
                  else if (c.cmd === '/context peek') runContextCommand('peek');
                }}
              >
                <span className="font-mono text-[12px] text-[#64D2FF]">{c.cmd}</span>
                <span className="text-[11px] text-[#F5F5F7]">{c.label}</span>
                <span className="text-[10px] text-[#8E8E93]">{c.hint}</span>
              </button>
            ))}
          </div>
        )}

        {showMenu && (
          <div className="absolute bottom-full left-0 z-10 mb-2 w-52 rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-1.5 shadow-xl">
            <p className="px-2 py-1 text-[10px] text-[#636366]">執行模式</p>
            {STRATEGIES.map((s) => (
              <button
                key={s.key}
                type="button"
                onClick={() => setExecutionStrategy(s.key)}
                className={`flex w-full rounded-lg px-2.5 py-1.5 text-left text-[12px] ${
                  executionStrategy === s.key
                    ? 'bg-[#0A84FF]/15 text-[#64B5FF]'
                    : 'text-[#AEAEB2] hover:bg-white/[0.04]'
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
              className="mt-1 w-full rounded-lg px-2.5 py-1.5 text-left text-[12px] text-[#AEAEB2] hover:bg-white/[0.04]"
            >
              進階選項…
            </button>
            <button
              type="button"
              className="mt-1 w-full rounded-lg px-2.5 py-1.5 text-left text-[12px] text-[#AEAEB2] hover:bg-white/[0.04] hover:text-[#64D2FF]"
              onClick={() => {
                setShowMenu(false);
                runContextCommand('detail');
              }}
            >
              Context 詳細區（/context）
            </button>
            <button
              type="button"
              className="mt-1 w-full rounded-lg px-2.5 py-1.5 text-left text-[12px] text-[#AEAEB2] hover:bg-white/[0.04] hover:text-[#64D2FF]"
              onClick={() => {
                setShowMenu(false);
                runContextCommand('peek');
              }}
            >
              Context Peek（/context peek）
            </button>
            <a
              href="#/monitor/integrations"
              className="mt-1 block w-full rounded-lg px-2.5 py-1.5 text-left text-[12px] text-[#AEAEB2] hover:bg-white/[0.04] hover:text-[#64D2FF]"
              onClick={() => setShowMenu(false)}
            >
              外部整合（MemOS／Viking…）
            </a>
          </div>
        )}

        {!compact && (
          <InputCreditBar
            text={text}
            strategy={executionStrategy}
            liveSpent={liveSpent}
            onOpenBilling={onOpenBilling}
          />
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
              className={`rounded-lg px-2 py-1 text-[11px] text-[#98989D] hover:bg-white/[0.04] hover:text-[#F5F5F7] ${
                showMenu ? 'bg-white/[0.06] text-[#F5F5F7]' : ''
              }`}
            >
              {strategyLabel}
            </button>

            <button
              type="submit"
              disabled={disabled || !text.trim() || insufficient}
              className="apple-send-btn ml-auto"
              aria-label={t('chat.send')}
              title={insufficient ? t('chat.insufficientBalance') : undefined}
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
