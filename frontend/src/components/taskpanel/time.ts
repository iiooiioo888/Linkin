/**
 * 相對時間顯示（剛剛／N 秒前／N 分鐘前／N 小時前）。
 */

export function elapsed(ts: number): string {
  const sec = Math.floor((Date.now() - ts * 1000) / 1000);
  if (sec < 5) return '剛剛';
  if (sec < 60) return `${sec} 秒前`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min} 分鐘前`;
  return `${Math.floor(min / 60)} 小時前`;
}
