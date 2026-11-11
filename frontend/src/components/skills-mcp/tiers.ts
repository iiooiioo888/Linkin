/**
 * 技能／MCP 條目分級（啟用／可用／需金鑰）與 MCP 健康度判定。
 */

import type { McpServerRecord, SkillRecord } from '../../api/client';

type SkillTier = 'enabled' | 'available' | 'needsKey';

export function skillTierOf(s: SkillRecord): SkillTier {
  if (s.skill_type === 'cursor-only') return 'needsKey';
  if (s.enabled) return 'enabled';
  return 'available';
}

export function mcpTierOf(s: McpServerRecord): SkillTier {
  const envIncomplete = Object.values(s.env ?? {}).some((v) => !v || v === '***' || v.includes('${'));
  const hdrIncomplete = Object.values(s.headers ?? {}).some((v) => !v || v === '***' || v.includes('${'));
  const configMissing = s.transport === 'stdio' ? !s.command.trim() : !s.url.trim();
  if (configMissing || envIncomplete || hdrIncomplete) return 'needsKey';
  const probe = s.last_probe as { ok?: boolean; probed_at?: string } | undefined;
  if (probe?.probed_at && !probe.ok) return 'needsKey';
  if (s.enabled) return 'enabled';
  return 'available';
}

export function mcpHealthLabel(s: McpServerRecord): 'ok' | 'warn' | 'unknown' {
  const probe = s.last_probe as { ok?: boolean; probed_at?: string } | undefined;
  if (!probe?.probed_at) return mcpTierOf(s) === 'needsKey' ? 'warn' : 'unknown';
  return probe.ok ? 'ok' : 'warn';
}
