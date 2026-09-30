# EvoLoop Backend Dockerfile
# 基底為 Python 3.12，執行 FastAPI + LangGraph 反思閉環
# 建置上下文為專案根目錄（docker-compose 中的 context: .）
FROM python:3.12-slim

ENV LANGGRAPH_STRICT_MSGPACK=true

WORKDIR /app

# 安裝系統依賴（chromadb 需要 g++ 編譯 hnswlib）
RUN apt-get update && apt-get install -y --no-install-recommends \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 安裝 Python 依賴（先複製 requirements 以利用 Docker 層快取）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製後端程式與共享模組
COPY backend/ ./backend/
COPY opc_service/ ./opc_service/

# 服務埠
EXPOSE 8000

# 健康檢查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# 啟動 FastAPI
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
