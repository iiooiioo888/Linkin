import { useMemo } from 'react';
import type { ModulePageProps } from '../types';
import ComposePanel from './ComposePanel';
import JobsPage from './JobsPage';
import ProjectDetailPage from './ProjectDetailPage';
import ProjectsPage from './ProjectsPage';
import ResourcesPage from './ResourcesPage';
import ReviewPage from './ReviewPage';
import ShotBoardPage from './ShotBoardPage';

type Tab = 'projects' | 'detail' | 'shots' | 'jobs' | 'review' | 'compose' | 'resources';

const TABS: ReadonlyArray<{ key: Tab; label: string }> = [
  { key: 'projects', label: '專案' },
  { key: 'detail', label: '詳情' },
  { key: 'shots', label: '鏡頭板' },
  { key: 'jobs', label: '任務' },
  { key: 'review', label: '審核' },
  { key: 'compose', label: '合成' },
  { key: 'resources', label: '資源' },
];

function tabFromPage(page: string | undefined): Tab {
  if (
    page === 'detail' ||
    page === 'shots' ||
    page === 'projects' ||
    page === 'jobs' ||
    page === 'review' ||
    page === 'compose' ||
    page === 'resources'
  ) {
    return page;
  }
  return 'projects';
}

export default function StudioHub({ page }: ModulePageProps) {
  const active = useMemo(() => tabFromPage(page), [page]);

  return (
    <div className="flex min-h-0 flex-1 flex-col" data-testid="lvs-hub">
      <nav className="flex flex-wrap gap-1 border-b border-[var(--console-line)] px-3 pt-2">
        {TABS.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            className={`px-3 py-2 text-[12px] ${
              active === key
                ? 'border-b-2 border-[var(--console-accent)] text-[var(--console-ink)]'
                : 'text-[var(--console-sub)]'
            }`}
            data-testid={`lvs-tab-${key}`}
            onClick={() => {
              window.location.hash =
                key === 'projects' ? '#/modules/local-video-studio' : `#/modules/local-video-studio/${key}`;
            }}
          >
            {label}
          </button>
        ))}
      </nav>
      {active === 'projects' ? <ProjectsPage /> : null}
      {active === 'detail' ? <ProjectDetailPage /> : null}
      {active === 'shots' ? <ShotBoardPage /> : null}
      {active === 'jobs' ? <JobsPage /> : null}
      {active === 'review' ? <ReviewPage /> : null}
      {active === 'compose' ? <ComposePanel /> : null}
      {active === 'resources' ? <ResourcesPage /> : null}
    </div>
  );
}
