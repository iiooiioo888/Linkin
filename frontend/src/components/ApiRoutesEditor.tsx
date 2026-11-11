/**
 * API 分割編輯器：多供應商（千問／DeepSeek／Kimi／OpenRouter）+ 每組多模型。
 *
 * 第五輪重構：實作已拆至 ./apiroutes-editor/*，此檔保留既有 import 路徑與公開 export
 * （default ApiRoutesEditor、PROVIDER_PRESETS、ProviderValue）。
 */
export { default } from './apiroutes-editor/ApiRoutesEditor';
export { PROVIDER_PRESETS } from './apiroutes-editor/presets';
export type { ProviderValue } from './apiroutes-editor/presets';
