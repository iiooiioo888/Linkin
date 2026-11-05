type RepoLink = {
  label: string;
  href: string;
  hint?: string;
  /** 可選公開演示站（與 repo 並列，不取代 GitHub 主連結） */
  liveHref?: string;
  liveLabel?: string;
};

const REPOS: RepoLink[] = [
  {
    label: 'Linkin（本 runtime）',
    href: 'https://github.com/iiooiioo888/Linkin',
  },
  {
    label: 'LinkinL（行销 · 本地执行版）',
    href: 'https://github.com/iiooiioo888/LinkinL',
    liveHref: 'https://iiooiioo888.github.io/LinkinL/',
    liveLabel: '线上站点',
  },
  {
    label: 'MediaCrawler（上游）',
    href: 'https://github.com/NanmiCoder/MediaCrawler',
    hint: '技能：.agents/skills/mediacrawler',
  },
  {
    label: 'Immich（可選圖庫）',
    href: 'https://immich.app/docs',
  },
  {
    label: 'PhotoPrism（可選圖库）',
    href: 'https://docs.photoprism.app/',
  },
];

export default function RelatedReposFooter() {
  return (
    <footer
      className="shrink-0 border-t border-[var(--console-line)] bg-[var(--console-sidebar)] px-4 py-2"
      data-testid="media-vault-related-repos"
    >
      <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-[var(--console-sub)]">相关仓库</p>
      <ul className="flex flex-wrap gap-x-3 gap-y-1 text-[11px]">
        {REPOS.map((repo) => (
          <li key={repo.href} className="inline-flex flex-wrap items-center gap-x-1">
            <a
              href={repo.href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[var(--console-accent)] hover:underline"
              title={repo.hint}
            >
              {repo.label}
            </a>
            {repo.liveHref ? (
              <>
                <span className="text-[var(--console-sub)]">·</span>
                <a
                  href={repo.liveHref}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[var(--console-accent)] hover:underline"
                >
                  {repo.liveLabel ?? '演示'}
                </a>
              </>
            ) : null}
          </li>
        ))}
      </ul>
    </footer>
  );
}

export function relatedRepoLabelsForTest(): string[] {
  return REPOS.map((r) => r.label);
}
