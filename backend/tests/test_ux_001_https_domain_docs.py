"""UX-001：HTTPS＋網域 docs／nginx example 存在性（不啟用產線 TLS）。"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUNBOOK = REPO / "docs" / "ops" / "ux-001-https-domain.md"
CONTRACT = REPO / "docs" / "contracts" / "ux-001-https-domain.md"
NGINX_EXAMPLE = REPO / "docs" / "ops" / "snippets" / "nginx-ux-001-tls.example.conf"

_BANNED_SECRET_MARKERS = (
    "BEGIN PRIVATE KEY",
    "BEGIN RSA PRIVATE KEY",
    "BEGIN EC PRIVATE KEY",
    "BEGIN OPENSSH PRIVATE KEY",
)


def test_ux001_runbook_exists_and_keywords() -> None:
    assert RUNBOOK.is_file(), f"runbook 不存在：{RUNBOOK}"
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "UX-001" in text
    assert "純 HTTP" in text or "HTTP＋" in text or "HTTP+" in text
    assert "does_not_enable_tls_on_prod" in text
    assert "wire_change" in text and "none" in text
    assert "ready_to_merge=false" in text or "`ready_to_merge=false`" in text
    assert "另授" in text
    assert "301" in text
    assert "不啟用產線" in text or "不**啟用產線" in text or "不真申請憑證" in text


def test_ux001_contract_exists_and_keywords() -> None:
    assert CONTRACT.is_file(), f"契約不存在：{CONTRACT}"
    text = CONTRACT.read_text(encoding="utf-8")
    assert "UX-001" in text
    assert "does_not_enable_tls_on_prod" in text
    assert "wire_change" in text and "none" in text
    assert "ready_to_merge=false" in text or "`ready_to_merge=false`" in text
    assert "nginx-ux-001-tls.example.conf" in text


def test_ux001_nginx_example_tls_shape() -> None:
    assert NGINX_EXAMPLE.is_file(), f"nginx example 不存在：{NGINX_EXAMPLE}"
    text = NGINX_EXAMPLE.read_text(encoding="utf-8")
    assert "listen 443 ssl" in text
    assert "server_name" in text
    assert "YOUR_DOMAIN" in text or "placeholder" in text.lower()
    assert "return 301" in text or "301" in text
    assert "ssl_certificate" in text
    assert "ssl_certificate_key" in text
    assert "does_not_enable_tls_on_prod" in text
    for marker in _BANNED_SECRET_MARKERS:
        assert marker not in text, f"example 不得含私鑰材料：{marker}"


def test_ux001_does_not_enable_tls_on_prod() -> None:
    """旗標：本票文件／example 明確不啟用產線 TLS。"""
    for path in (RUNBOOK, CONTRACT, NGINX_EXAMPLE):
        text = path.read_text(encoding="utf-8")
        assert "does_not_enable_tls_on_prod" in text, f"{path} 缺 does_not_enable_tls_on_prod"
    # 產線實際啟用檔 frontend/nginx.conf 仍應維持僅 80（本票不改）
    prod_nginx = (REPO / "frontend" / "nginx.conf").read_text(encoding="utf-8")
    assert "listen 80" in prod_nginx
    assert "listen 443" not in prod_nginx
    assert "ssl_certificate" not in prod_nginx
