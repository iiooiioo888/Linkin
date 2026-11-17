import type { ComponentType } from 'react';
import { ContextCompressionPage } from '../../surfaces/context-compression/Page';

export const id = 'context-compression';
export const label = '上下文壓縮';
export const Page: ComponentType = ContextCompressionPage;

const mount = { id, label, Page };

export default mount;
