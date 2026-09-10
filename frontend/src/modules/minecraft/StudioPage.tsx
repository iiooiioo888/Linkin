import AgentsMonitorPanel from '../../components/AgentsMonitorPanel';
import type { ModulePageProps } from '../types';

export default function StudioPage({ focusAgentId, onFocusAgent }: ModulePageProps) {
  return <AgentsMonitorPanel focusAgentId={focusAgentId} onFocusAgent={onFocusAgent} deskScope="studio" />;
}
