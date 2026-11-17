/**
 * 首次登入後可關閉的「開始任務」導覽橫幅。
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { dismissOnboarding, isOnboardingDismissed } from '../../lib/onboarding';

interface OnboardingGuideProps {
  onStartChat?: () => void;
}

export default function OnboardingGuide(_props: OnboardingGuideProps) {
  const { t } = useTranslation();
  const [visible, setVisible] = useState(() => !isOnboardingDismissed());

  if (!visible) return null;

  const close = () => {
    dismissOnboarding();
    setVisible(false);
  };

  const body = t('onboarding.body');
  const splitAt = body.indexOf('。');
  const lead = splitAt >= 0 && splitAt < body.length - 1 ? body.slice(0, splitAt + 1) : body;
  const mode = splitAt >= 0 && splitAt < body.length - 1 ? body.slice(splitAt + 1) : '';

  return (
    <div
      className="flex shrink-0 items-center justify-between gap-3 border-b border-[var(--console-line)] px-4 py-2 sm:px-6"
      data-testid="onboarding-guide"
      role="status"
    >
      <p className="min-w-0 text-[12px] leading-normal text-[var(--console-sub)]">
        {lead}
        {mode ? <span className="whitespace-nowrap">{mode}</span> : null}
      </p>
      <button
        type="button"
        onClick={close}
        className="shrink-0 rounded-md px-2 py-1 text-[12px] text-[var(--console-sub)] hover:text-[var(--console-ink)]"
      >
        {t('common.dismiss')}
      </button>
    </div>
  );
}
