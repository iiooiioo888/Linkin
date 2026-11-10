const REPOS = [
  {
    label: 'Linkin（本 runtime）',
    href: 'https://github.com/iiooiioo888/Linkin',
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
    label: 'PhotoPrism（可選圖庫）',
    href: 'https://docs.photoprism.app/',
  },
] as const;

export default function RelatedReposFooter() {
  return (
    <footer
      className="shrink-0 border-t border-[var(--console-line)] bg-[var(--console-sidebar)] px-4 py-2"
      data-testid="media-vault-related-repos"
    >
      <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-[var(--console-sub)]">相關倉庫</p>
      <ul className="flex flex-wrap gap-x-3 gap-y-1 text-[11px]">
        {REPOS.map((repo) => (
          <li key={repo.href}>
            <a
              href={repo.href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[var(--console-accent)] hover:underline"
              title={'hint' in repo ? repo.hint : undefined}
            >
              {repo.label}
            </a>
          </li>
        ))}
      </ul>
    </footer>
  );
}

export function relatedRepoLabelsForTest(): string[] {
  return REPOS.map((r) => r.label);
}
