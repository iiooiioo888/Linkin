/**
 * 控制台版面共用型別：div 基底 props 與 section 導航項目。
 */

import type { HTMLAttributes } from 'react';

export type DivProps = HTMLAttributes<HTMLDivElement>;

export type SectionNavItem = { id: string; label: string };
