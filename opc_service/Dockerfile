# EvoLoop OPC Service Dockerfile
# 基底為 Python 3.12，執行 OPC UA 工業數據微服務
# 建置上下文為專案根目錄（docker-compose 中的 context: .）
FROM python:3.12-slim

ENV LANGGRAPH_STRICT_MSGPACK=true

WORKDIR /app

# 安裝 Python 依賴（先複製 requirements 以利用 Docker 層快取）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製 OPC 服務程式
COPY opc_service/ ./opc_service/

# 服務埠
EXPOSE 8001

# 健康檢查
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/opc/health')" || exit 1

# 啟動 FastAPI
CMD ["uvicorn", "opc_service.main:app", "--host", "0.0.0.0", "--port", "8001"]
