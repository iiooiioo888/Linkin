/**
 * IntegrationsPanel — MemOS／OpenViking／WeKnora／Yao／Ouroboros／OpenPencil 控制台。
 *
 * 第七輪重構：實作已拆至 ./integrations/*，此檔保留既有 import 路徑與 default export
 * （MonitorView 以 lazy(() => import('./IntegrationsPanel')) 動態載入，須維持 default）。
 */
export { default } from './integrations/IntegrationsPanel';
