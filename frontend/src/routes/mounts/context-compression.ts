import { ContextCompressionPage } from '../../surfaces/context-compression/Page';
import { CONTEXT_COMPRESSION_ID, CONTEXT_COMPRESSION_LABEL } from '../../surfaces/context-compression/gap';

export const id = CONTEXT_COMPRESSION_ID;
export const label = CONTEXT_COMPRESSION_LABEL;
export const Page = ContextCompressionPage;

const mount = { id, label, Page };

export default mount;
