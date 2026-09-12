/**
 * 首次登入後可關閉的「開始任務」導覽橫幅。
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { dismissOnboarding, isOnboardingDismissed } from '../../lib/onboarding';

interface OnboardingGuideProps {
  onStartChat?: () => void;
}

export default function OnboardingGuide({ onStartChat }: OnboardingGuideProps) {
  const { t } = useTranslation();
  const [visible, setVisible] = useState(() => !isOnboardingDismissed());

  if (!visible) return null;

  const close = () => {
    dismissOnboarding();
    setVisible(false);
  };

  return (
    <div
      className="shrink-0 border-b border-[color-mix(in_srgb,var(--console-accent)_25%,transparent)] bg-[color-mix(in_srgb,var(--console-accent)_8%,transparent)] px-4 py-3 sm:px-6"
      data-testid="onboarding-guide"
      role="region"
      aria-label={t('onboarding.title')}
    >
      <div className="mx-auto flex max-w-3xl flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <p className="text-[13px] font-semibold text-[var(--console-ink)]">{t('onboarding.title')}</p>
          <p className="mt-0.5 text-[11px] text-[var(--console-sub)]">{t('onboarding.body')}</p>
          <p className="mt-1 text-[10px] text-[var(--console-faint)]">{t('onboarding.monitorNote')}</p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => {
              onStartChat?.();
              close();
            }}
            className="rounded-lg bg-[color-mix(in_srgb,var(--console-accent)_22%,transparent)] px-3 py-1.5 text-[11px] font-medium text-[var(--console-accent)] ring-1 ring-[color-mix(in_srgb,var(--console-accent)_35%,transparent)] hover:bg-[color-mix(in_srgb,var(--console-accent)_30%,transparent)]"
          >
            {t('onboarding.startCta')}
          </button>
          <button
            type="button"
            onClick={close}
            className="rounded-lg px-2.5 py-1.5 text-[11px] text-[var(--console-sub)] hover:bg-white/[0.04] hover:text-[var(--console-ink)]"
          >
            {t('common.dismiss')}
          </button>
        </div>
      </div>
    </div>
  );
}
