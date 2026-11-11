/**
 * DockerView — Docker 容器管理 GUI。
 *
 * 提供容器状态监控、资源统计、健康检查、日志查看与启停控制。
 * 每 8 秒自动刷新状态，支持手动刷新。
 * 采用阿里雲式按時計費：每個容器顯示小時費率與累計費用。
 *
 * 安全控制：仅 Manager/DevOps 可执行写操作（重启/停止/启动）。
 * 前端层面做二次确认，后端由 DockerManager 安全护栏兜底。
 *
 * 第四輪重構：實作已拆至 ./dockerview/ 套件，此檔保留既有匯入路徑與預設匯出。
 */
export { default } from './dockerview/DockerView';
