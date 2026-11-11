/**
 * LiveBoard — Agent Desk 觀測總覽（monitor dashboard v3）。
 *
 * 第三輪重構：實作已拆至 ./liveboard/*，此檔保留既有 import 路徑與公開 export
 * （default LiveBoard、LiveBoardDensity、LiveBoardNav）。
 */
export { default } from './liveboard/LiveBoard';
export type { LiveBoardDensity, LiveBoardNav } from './liveboard/types';
