/**
 * 上游專案連結膠囊。
 */

export function UpstreamLink({ name, url }: { name: string; url: string }) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="rounded-full border border-white/[0.08] px-2 py-0.5 text-[10px] text-[var(--console-sub)] transition-colors hover:border-[color-mix(in_srgb,var(--console-accent)_40%,transparent)] hover:text-[var(--console-accent)]"
    >
      {name} ↗
    </a>
  );
}
