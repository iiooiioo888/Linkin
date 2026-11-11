/**
 * SkillsMcpPanel — 技能庫與 MCP 連線管理。
 *
 * 技能 = 注入角色提示詞的可重用知識（方法論／流程／領域指引）。
 * MCP  = 通用 Model Context Protocol server 連線（stdio/sse/http），
 *        探測後工具自動掛進公司工具註冊表，角色可經 tool_call 閉環調用。
 *
 * 原始單檔已拆至本套件；index.ts 維持既有公開 API（default export）。
 */
export { default } from './SkillsMcpPanel';
