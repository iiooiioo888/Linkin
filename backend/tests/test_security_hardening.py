"""回歸：預設登入秘密、資料埠與 OPC 開發重載不要再回到倉庫。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_BANNED = (
    "ID_PARTS",
    "SECRET_PARTS",
    "matchPeeled",
    "1f4ac7b757bc42f0",
    "9a9e35eac9af48e1",
    "d426fee8d6ae4a89",
)


def test_client_sources_do_not_embed_gate_material():
    roots = [ROOT / "frontend" / "src", ROOT / "frontend" / "e2e", ROOT / "backend" / "auth"]
    for root in roots:
        for path in root.rglob("*"):
            if path.suffix not in {".ts", ".tsx", ".js", ".py"}:
                continue
            text = path.read_text(encoding="utf-8")
            for item in _BANNED:
                assert item not in text, f"{path} 含有 {item}"


def test_compose_binds_data_ports_to_loopback():
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "127.0.0.1:6379:6379" in text
    assert "127.0.0.1:8100:8000" in text
    assert "127.0.0.1:8001:8001" in text
    assert "chromadb/chroma:latest" not in text
    assert "chromadb/chroma:1.0.0" in text
    assert "OPC_SIM_ENABLED=false" in text
    assert "--requirepass" in text


def test_nginx_sets_security_headers():
    text = (ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")
    assert "Content-Security-Policy" in text
    assert "X-Content-Type-Options" in text
    assert "X-Frame-Options" in text
    assert "Referrer-Policy" in text
    assert "Strict-Transport-Security" not in text


def test_opc_entrypoint_does_not_reload():
    text = (ROOT / "opc_service" / "main.py").read_text(encoding="utf-8")
    assert "reload=True" not in text
    assert "reload=False" in text
