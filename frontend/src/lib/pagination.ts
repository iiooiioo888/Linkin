import { useEffect, useMemo, useState } from 'react';

/** 將陣列切成指定頁 */
export function paginateSlice<T>(items: T[], page: number, pageSize: number): T[] {
  if (pageSize <= 0) return items;
  const start = (page - 1) * pageSize;
  return items.slice(start, start + pageSize);
}

export function totalPages(count: number, pageSize: number): number {
  if (pageSize <= 0) return 1;
  return Math.max(1, Math.ceil(count / pageSize));
}

/** 列表分頁狀態（換頁，不滾動） */
export function usePagination<T>(items: T[], pageSize: number) {
  const [page, setPage] = useState(1);
  const pages = totalPages(items.length, pageSize);

  useEffect(() => {
    if (page > pages) setPage(pages);
  }, [page, pages]);

  const slice = useMemo(() => paginateSlice(items, page, pageSize), [items, page, pageSize]);

  return {
    page,
    pages,
    slice,
    setPage,
    prev: () => setPage((p) => Math.max(1, p - 1)),
    next: () => setPage((p) => Math.min(pages, p + 1)),
    reset: () => setPage(1),
  };
}

/** 固定頁數內容切換（非列表） */
export function useFixedPages(count: number) {
  const pages = Math.max(1, count);
  const [page, setPage] = useState(1);
  const safe = Math.min(Math.max(1, page), pages);

  useEffect(() => {
    if (page > pages) setPage(pages);
  }, [page, pages]);

  return {
    page: safe,
    pages,
    setPage,
    prev: () => setPage((p) => Math.max(1, p - 1)),
    next: () => setPage((p) => Math.min(pages, p + 1)),
  };
}
