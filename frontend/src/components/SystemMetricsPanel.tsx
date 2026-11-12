/**
 * SystemMetricsPanel — 系統總覽（OCD 三欄 · 非工業 OPC）。
 *
 * 彙總反思閉環、快取、路由、Trace、任務運行時等 Linkin 自身指標。
 *
 * 第十輪重構：實作已拆至 ./systemmetrics/ 套件，此檔保留既有匯入路徑與預設匯出。
 */
export { default } from './systemmetrics/SystemMetricsPanel';
