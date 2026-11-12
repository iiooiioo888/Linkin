/**
 * 卡片容器（ConsoleCard 系列）、空狀態與 rd-shell 外殼。
 */

import { consoleLayout } from '../../../lib/consoleLayout';
import { cn } from './cn';
import type { DivProps } from './types';

export function ConsoleCard({ className, children, ...rest }: DivProps) {
  return (
    <div className={cn(consoleLayout.card, className)} {...rest}>
      {children}
    </div>
  );
}

export function ConsoleCardHeader({ className, children, ...rest }: DivProps) {
  return (
    <p className={cn(consoleLayout.cardHeader, className)} {...rest}>
      {children}
    </p>
  );
}

export function ConsoleCardBody({
  dense,
  className,
  children,
  ...rest
}: DivProps & { dense?: boolean }) {
  return (
    <div
      className={cn(dense ? consoleLayout.cardBodyDense : consoleLayout.cardBody, className)}
      {...rest}
    >
      {children}
    </div>
  );
}

export function ConsoleEmpty({
  className,
  children,
  compact,
  ...rest
}: DivProps & { compact?: boolean }) {
  return (
    <div className={cn(compact ? consoleLayout.emptySm : consoleLayout.empty, className)} {...rest}>
      {children}
    </div>
  );
}

/** 控制台內的 rd-shell 外殼（角色／管線／任務共用骨架，外緣 padding 對齊 pagePadding） */
export function ConsoleRdShell({ className, children, ...rest }: DivProps) {
  return (
    <div className={cn(consoleLayout.rdShell, className)} {...rest}>
      {children}
    </div>
  );
}
