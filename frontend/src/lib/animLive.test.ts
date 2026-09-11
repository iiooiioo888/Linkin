import { describe, expect, it } from 'vitest';
import { mapPhaseToDagNodeId, mapPhaseToPipelineIndex } from './animLive';

describe('mapPhaseToPipelineIndex', () => {
  it('maps recall and memory phases to 感知', () => {
    expect(mapPhaseToPipelineIndex('retrieve_memories')).toBe(0);
    expect(mapPhaseToPipelineIndex('enhance_recall_context')).toBe(0);
  });

  it('maps improve to 輸出 not 生成', () => {
    expect(mapPhaseToPipelineIndex('improve')).toBe(5);
    expect(mapPhaseToPipelineIndex('improve_answer')).toBe(5);
  });

  it('maps final_review to 輸出 not 評估', () => {
    expect(mapPhaseToPipelineIndex('final_review')).toBe(5);
  });

  it('maps company execution to 生成', () => {
    expect(mapPhaseToPipelineIndex('execute_review')).toBe(2);
    expect(mapPhaseToPipelineIndex('campaign_plan')).toBe(1);
  });
});

describe('mapPhaseToDagNodeId', () => {
  it('routes company phases to company node', () => {
    expect(mapPhaseToDagNodeId('execute_review')).toBe('company');
    expect(mapPhaseToDagNodeId('improve')).toBe('improve');
  });
});
