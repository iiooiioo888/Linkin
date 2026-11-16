import type { ConcretePath } from '../lib/executionPath';
import { PATH_LABEL } from '../lib/executionPath';
import type { PathSuggestion } from '../api/client';

interface PathSuggesterProps {
  suggestion: PathSuggestion | null;
  loading: boolean;
  allowChoice: boolean;
  onUse: (path: ConcretePath) => void;
  onMakeDefault: (path: ConcretePath) => void;
}

/** 路徑建議器：展示建議與理由。按下按鈕才送出，建議本身不執行。 */
export default function PathSuggester({
  suggestion,
  loading,
  allowChoice,
  onUse,
  onMakeDefault,
}: PathSuggesterProps) {
  if (!suggestion && !loading) return null;
  const locked = Boolean(suggestion?.locked);
  const suggested = suggestion?.suggested;
  const reason = suggestion?.reason_text || suggestion?.reason || '';

  return (
    <div
      className="mb-2 rounded-xl border border-white/[0.08] bg-[var(--console-card)] px-3 py-2"
      data-testid="path-suggester"
    >
      <p className="text-[12px] text-[var(--console-ink)]">
        {loading && !suggestion
          ? '正在看這則內容適合哪條路徑…'
          : `系統建議：${suggested ? PATH_LABEL[suggested] : '—'}`}
      </p>
      {reason && <p className="mt-0.5 text-[11px] text-[var(--console-sub)]">{reason}</p>}
      {locked && (
        <p className="mt-1 text-[11px] text-[var(--console-danger,var(--console-ink))]">
          管理員已鎖定為公司分析，不能改走簡單生成。
        </p>
      )}
      <div className="mt-2 flex flex-wrap gap-1.5">
        <button
          type="button"
          disabled={!allowChoice || locked}
          onClick={() => onUse('simple')}
          className="rounded-lg px-2.5 py-1 text-[12px] text-[var(--console-ink)] hover:bg-white/[0.06] disabled:opacity-40"
        >
          本次使用簡單生成
        </button>
        <button
          type="button"
          disabled={!allowChoice && !locked}
          onClick={() => onUse('company')}
          className="rounded-lg px-2.5 py-1 text-[12px] text-[var(--console-ink)] hover:bg-white/[0.06] disabled:opacity-40"
        >
          本次使用公司分析
        </button>
        <button
          type="button"
          disabled={!suggested || (locked && suggested === 'simple')}
          onClick={() => suggested && onMakeDefault(locked ? 'company' : suggested)}
          className="rounded-lg px-2.5 py-1 text-[12px] text-[var(--console-sub)] hover:bg-white/[0.06] hover:text-[var(--console-ink)] disabled:opacity-40"
        >
          設為默認
        </button>
      </div>
    </div>
  );
}
