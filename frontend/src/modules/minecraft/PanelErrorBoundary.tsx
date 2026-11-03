import { Component, type ErrorInfo, type ReactNode } from 'react';

type Props = {
  title?: string;
  children: ReactNode;
};

type State = { error: Error | null };

/** 模組面板局部錯誤邊界：子樹 throw 時不拆掉整棵 App。 */
export class PanelErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('[PanelErrorBoundary]', error, info.componentStack);
  }

  private reset = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    const { error } = this.state;
    if (error) {
      return (
        <div
          className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 shadow-[inset_0_1px_0_rgba(201,169,97,0.06)]"
          role="alert"
        >
          <h3 className="text-sm font-semibold text-red-300">{this.props.title ?? '此面板發生錯誤'}</h3>
          <p className="mt-2 text-[11px] leading-relaxed text-[var(--console-faint)]">{error.message}</p>
          <button
            type="button"
            onClick={this.reset}
            className="mt-3 rounded-lg border border-[color-mix(in_srgb,var(--console-accent)_40%,transparent)] bg-[color-mix(in_srgb,var(--console-accent)_10%,transparent)] px-3 py-1.5 text-[12px] text-[var(--console-accent)] hover:bg-[color-mix(in_srgb,var(--console-accent)_15%,transparent)]"
          >
            重試
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
