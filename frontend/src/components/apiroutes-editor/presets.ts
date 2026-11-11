/**
 * API 路由編輯器：供應商預設清單與 ProviderValue 型別。
 */
import { TOKEN_PLAN_LABEL } from '../../lib/llmCatalog';

export const PROVIDER_PRESETS = [
  {
    value: 'token-plan',
    label: TOKEN_PLAN_LABEL,
    apiBase: 'https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1',
    defaultModel: 'qwen3.8-flash',
    hint: '阿里雲 Token Plan MaaS（多廠商：Qwen／DeepSeek／GLM／Wan 等）；與 DashScope 通義千問不同',
    models: [] as string[],
  },
  {
    value: 'qwen',
    label: '通義千問 Qwen',
    apiBase: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    defaultModel: 'qwen3.8-flash',
    hint: '最新 qwen3.8／3.7 系列（1M 上下文）；舊 qwen-plus／max 仍可勾選；qwen3.8-max 已 sunset 自預設剔除',
    models: [
      'qwen3.8-flash',
      'qwen3.7-plus',
      'qwen3.7-flash',
      'qwen3-coder-plus',
      'qwen-long',
      'qwen-plus',
      'qwen-max',
      'qwen-turbo',
    ],
  },
  {
    value: 'deepseek',
    label: 'DeepSeek',
    apiBase: 'https://api.deepseek.com',
    defaultModel: 'deepseek-v4-pro',
    hint: '單一廠商；可與千問、OpenRouter 同時存在；deepseek-v4-flash 已 sunset 自預設剔除',
    models: ['deepseek-v4-pro', 'deepseek-v4-flash-vision-exp'],
  },
  {
    value: 'moonshot',
    label: 'Moonshot / Kimi',
    apiBase: 'https://api.moonshot.cn/v1',
    defaultModel: 'kimi-k2.7-code',
    hint: 'kimi-k2／moonshot-v1 與 kimi-k3（sunset）已自現行預設剔除；請用 K2.7 Code／K2.6',
    models: ['kimi-k2.7-code', 'kimi-k2.6'],
  },
  {
    value: 'openrouter',
    label: 'OpenRouter（通用目錄）',
    apiBase: 'https://openrouter.ai/api/v1',
    defaultModel: '',
    hint: '一個金鑰對應數百個模型；儲存後爬取 /models（已排除 Claude）',
    models: [] as string[],
  },
  {
    value: 'openai',
    label: 'OpenAI',
    apiBase: 'https://api.openai.com/v1',
    defaultModel: 'gpt-5.6-terra',
    hint: 'gpt-4o／4.1 已退役；gpt-5.6-sol 已 sunset 自預設剔除；現行為 GPT-6／GPT-5.6 terra／luna',
    models: ['gpt-6-astra', 'gpt-5.6-terra', 'gpt-5.6-luna'],
  },
  {
    value: 'zhipu',
    label: '智譜 GLM',
    apiBase: 'https://open.bigmodel.cn/api/paas/v4',
    defaultModel: 'glm-5.3-flash',
    hint: 'glm-5.3 已 sunset 自預設剔除；現行建議 GLM-5.3-flash／5.1／5',
    models: ['glm-5.3-flash', 'glm-5.1', 'glm-5', 'glm-5.2'],
  },
  {
    value: 'ollama',
    label: 'Ollama（本地）',
    apiBase: 'http://127.0.0.1:11434/v1',
    defaultModel: '',
    hint: '儲存後爬取本機 /v1/models',
    models: [] as string[],
  },
  {
    value: 'custom',
    label: '自訂（OpenAI 相容）',
    apiBase: '',
    defaultModel: '',
    hint: 'vLLM / 閘道等相容端點',
    models: [] as string[],
  },
] as const;

export type ProviderValue = (typeof PROVIDER_PRESETS)[number]['value'];
