/** 輸入列：送出前可見路徑切換，建議只預選、按下才送。支援 /context 斜線命令。 */
import { useEffect, useMemo, useRef, useState } from 'react';
import type { FormEvent, KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { COMPANY_TEMPLATES } from '../types';
import type { RoutingPreviewSnapshot } from '../lib/routingPreview';
import type { CompanyTemplate, TaskOptions } from '../types';
import { openChatContextDetail, openContextModal } from '../lib/contextUi';
import { usePathSuggestion } from '../hooks/usePathSuggestion';
import { fetchExecutionPathSettings, saveExecutionPathDefault } from '../api/client';
import {
  PATH_LABEL,
  readSessionPathChoice,
  strategyForChoice,
  writeSessionPathChoice,
  type ConcretePath,
  type PathChoice,
} from '../lib/executionPath';
import PathSuggester from './PathSuggester';

export interface SendOptions {
  executionStrategy: 'simple' | 'company' | 'user_default';
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

const PATHS: { key: ConcretePath; label: string }[] = [
  { key: 'simple', label: PATH_LABEL.simple },
  { key: 'company', label: PATH_LABEL.company },
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
  const [pathChoice, setPathChoice] = useState<PathChoice | null>(() => readSessionPathChoice());
  const [allowChoice, setAllowChoice] = useState(true);
  const [choiceHint, setChoiceHint] = useState('');
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

  const { suggestion, loading: suggestionLoading } = usePathSuggestion(text);
  const locked = Boolean(suggestion?.locked);
  const selectedPath: ConcretePath | null = locked ? 'company' : pathChoice?.path ?? null;

  useEffect(() => {
    let cancelled = false;
    void fetchExecutionPathSettings()
      .then((settings) => {
        if (cancelled) return;
        setAllowChoice(settings.allow_user_path_choice !== false);
        const stored = readSessionPathChoice();
        if (stored?.source === 'session') {
          setPathChoice(stored);
          return;
        }
        if (settings.default_execution_strategy === 'simple' || settings.default_execution_strategy === 'company') {
          const next: PathChoice = { source: 'default', path: settings.default_execution_strategy };
          setPathChoice(next);
          writeSessionPathChoice(next);
        }
      })
      .catch(() => {
        /* 設定讀取失敗時仍可手動選路徑 */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const remember = (next: PathChoice) => {
    setPathChoice(next);
    writeSessionPathChoice(next);
    setChoiceHint(next.source === 'default' ? '已設為默認，送出前仍可切換' : '只用於這次');
  };

  const selectPath = (path: ConcretePath, source: PathChoice['source']) => {
    if (!allowChoice && source === 'session' && !locked) return;
    if (locked && path === 'simple') return;
    remember({ source, path: locked ? 'company' : path });
  };

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

  const sendWith = (choice: PathChoice, rawText: string) => {
    const trimmed = rawText.trim();
    if (!trimmed || disabled) return;
    const taskOptions: TaskOptions = {};
    if (budgetLimit) taskOptions.budget_limit = parseFloat(budgetLimit);
    if (maxParallel) taskOptions.max_parallel = parseInt(maxParallel, 10);
    if (maxIterations) taskOptions.max_iterations = parseInt(maxIterations, 10);
    if (maxReviewRounds) taskOptions.max_review_rounds = parseInt(maxReviewRounds, 10);
    if (passThreshold) taskOptions.pass_threshold = parseFloat(passThreshold);
    const path = locked ? 'company' : choice.path;
    onSend(trimmed, {
      executionStrategy: locked ? 'company' : strategyForChoice({ ...choice, path }),
      companyTemplate,
      taskOptions,
    });
    setText('');
    setChoiceHint('');
    setShowMenu(false);
    requestAnimationFrame(() => {
      if (textareaRef.current) textareaRef.current.style.height = 'auto';
    });
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
    const choice: PathChoice | null = locked
      ? { source: 'session', path: 'company' }
      : pathChoice;
    if (!choice) {
      setChoiceHint('請先選擇簡單生成或公司分析');
      return;
    }
    sendWith(choice, trimmed);
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
      <div className="relative w-full">
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
            <p className="px-2 py-1 text-[10px] text-[var(--console-sub)]">公司模板</p>
            {(selectedPath === 'company' || locked) && (
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
          </div>
        )}

        <PathSuggester
          suggestion={suggestion}
          loading={suggestionLoading}
          allowChoice={allowChoice}
          onUse={(path) => {
            const next: PathChoice = { source: 'session', path: locked ? 'company' : path };
            remember(next);
            sendWith(next, text);
          }}
          onMakeDefault={(path) => {
            const target = locked ? 'company' : path;
            void saveExecutionPathDefault(target)
              .then(() => remember({ source: 'default', path: target }))
              .catch((err: unknown) => setChoiceHint(err instanceof Error ? err.message : '儲存默認失敗'));
          }}
        />

        <div className="mb-2 flex flex-wrap items-center gap-1.5" role="group" aria-label="執行路徑" data-testid="path-switcher">
          {PATHS.map((item) => {
            const active = selectedPath === item.key;
            const blocked = (!allowChoice && !locked) || (locked && item.key === 'simple');
            return (
              <button
                key={item.key}
                type="button"
                aria-pressed={active}
                disabled={disabled || blocked}
                onClick={() => selectPath(item.key, 'session')}
                className={`path-choice${active ? ' is-on' : ''}`}
              >
                {item.label}
              </button>
            );
          })}
          {pathChoice?.source === 'default' && !locked && (
            <span className="text-[11px] text-[var(--console-faint)]">目前是默認，仍可切換</span>
          )}
          {choiceHint && <span className="text-[11px] text-[var(--console-sub)]">{choiceHint}</span>}
        </div>

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
              className={`apple-composer__more${showMenu ? ' is-on' : ''}`}
              aria-label={selectedPath === 'company' ? '模板' : '選項'}
              aria-expanded={showMenu}
            >
              {selectedPath === 'company' ? '模板' : '選項'}
            </button>

            <button
              type="submit"
              disabled={disabled || !text.trim()}
              className="apple-send-btn ml-auto"
              aria-label={t('chat.send')}
            >
              {disabled ? <span className="apple-send-btn__spinner" /> : t('chat.send')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
