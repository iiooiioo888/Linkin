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
