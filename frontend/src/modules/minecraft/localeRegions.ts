/** 敘事區域 canonical 值（後端／資料）與繁中 UI 標籤 */
export const NARRATIVE_REGION_OPTIONS: Array<{ value: string; label: string }> = [
  { value: '织庭都', label: '織庭都' },
  { value: '精灵森林', label: '精靈森林' },
  { value: '裂隙港', label: '裂隙港' },
  { value: '宁渊谷', label: '寧淵谷' },
];

export function narrativeRegionLabel(value: string): string {
  return NARRATIVE_REGION_OPTIONS.find((o) => o.value === value)?.label ?? value;
}

const DISPLAY_LABELS: Record<string, string> = {
  主线: '主線',
  支线: '支線',
  日常: '日常',
  简单: '簡單',
  普通: '普通',
  困难: '困難',
  common: '普通',
  uncommon: '優良',
  rare: '稀有',
  epic: '史詩',
  legendary: '傳說',
};

/** 資料值維持後端原文，畫面上改成繁中。 */
export function mcLabel(value: string): string {
  return DISPLAY_LABELS[value] ?? narrativeRegionLabel(value);
}
