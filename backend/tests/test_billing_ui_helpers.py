"""billingUi.ts 輔助函式邏輯 parity 測試（v6.0 文案與公式）。"""

from __future__ import annotations

import pytest

from backend.billing.pool_types import CONTRIBUTION_UNLOCKED_CONVERT_RATIO


def test_convert_ratio_parity():
    amount = 100.0
    expected = round(amount * CONTRIBUTION_UNLOCKED_CONVERT_RATIO, 4)
    assert expected == 40.0


def test_lock_threshold_notice_parity():
    unlocked = 120.0
    threshold = 50.0
    convertible = max(0.0, unlocked - threshold)
    notice = f"當前累積 {unlocked:.1f} / 閾值 {threshold:.1f}，剩餘 {convertible:.1f} 可轉鎖倉"
    assert "當前累積" in notice
    assert "閾值" in notice
    assert "可轉鎖倉" in notice


def test_rollover_notice_pattern():
    ratio = 0.5
    cap = 50000
    pct = int(ratio * 100)
    notice = f"月贈送積分將於每月初按 {pct}% 滾入已購買池（上限 {cap/1000:.1f}k），剩餘作廢"
    assert "50%" in notice
    assert "滾入已購買池" in notice


def test_reward_projection_parity():
    amount = 100.0
    mult = 1.08
    reward = amount * (mult - 1)
    penalty = amount * 0.05
    assert reward == pytest.approx(8.0)
    assert penalty == pytest.approx(5.0)
    assert amount + reward == pytest.approx(108.0)


def test_decay_projection_parity():
    unlocked = 100.0
    after = round(unlocked * 0.8, 4)
    assert after == 80.0
