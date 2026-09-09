/** 輸入列：極簡 composer，模式收在選單內。 */
import { useRef, useState } from 'react';
import type { FormEvent, KeyboardEvent } from 'react';
import { COMPANY_TEMPLATES } from '../types';
import type { CompanyTemplate, TaskOptions } from '../types';

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
}

const STRATEGIES: { key: 'auto' | 'simple' | 'company'; label: string }[] = [
  { key: 'auto', label: '自動' },
  { key: 'simple', label: '簡單' },
  { key: 'company', label: '公司' },
];

export default function InputBar({ disabled, onSend, compact = false }: InputBarProps) {
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
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const strategyLabel = STRATEGIES.find((s) => s.key === executionStrategy)?.label ?? '自動';

  const autoResize = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
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
          </div>
        )}

        <form onSubmit={handleSubmit} className="apple-composer">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              autoResize();
            }}
            onKeyDown={handleKeyDown}
            placeholder={compact ? '輸入訊息給 Agent...' : '輸入問題…'}
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
              disabled={disabled || !text.trim()}
              className="apple-send-btn ml-auto"
              aria-label="發送"
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
