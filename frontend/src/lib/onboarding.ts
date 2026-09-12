/** 首次使用導覽旗標（localStorage）。 */

const ONBOARDING_KEY = 'linkin.onboarding.dismissed';
const CHAT_EMPTY_HINT_KEY = 'linkin.chat.emptyHint.dismissed';

export function isOnboardingDismissed(): boolean {
  try {
    return localStorage.getItem(ONBOARDING_KEY) === '1';
  } catch {
    return false;
  }
}

export function dismissOnboarding(): void {
  try {
    localStorage.setItem(ONBOARDING_KEY, '1');
  } catch {
    /* ignore */
  }
}

export function isChatEmptyHintDismissed(): boolean {
  try {
    return localStorage.getItem(CHAT_EMPTY_HINT_KEY) === '1';
  } catch {
    return false;
  }
}

export function dismissChatEmptyHint(): void {
  try {
    localStorage.setItem(CHAT_EMPTY_HINT_KEY, '1');
  } catch {
    /* ignore */
  }
}
