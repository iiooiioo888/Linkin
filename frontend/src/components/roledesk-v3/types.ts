/**
 * RoleV3Desk 公開 props 型別。
 */

import type { GrillTreeNode, L0Snapshot, RahoSnapshot, RoleAgent } from '../../types';

export interface RoleV3DeskProps {
  agent: RoleAgent;
  agents: RoleAgent[];
  rahoSnap: RahoSnapshot | null;
  grillNodes: GrillTreeNode[];
  l0: L0Snapshot | null;
  onSelectAgent: (id: string) => void;
  onOpenGrill: () => void;
}
