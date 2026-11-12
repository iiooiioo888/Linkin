/**
 * className 串接 helper（過濾 false／null／undefined）。
 */

export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ');
}
