# EvoLoop Backend ??Dockerfile
# ?ºä? Python 3.12ï¼Œè?è¡?FastAPI + LangGraph ?æ€é—­??
# ?„å»ºä¸Šä??‡ï?é¡¹ç›®?¹ç›®å½•ï?docker-compose ä¸­æ?å®?context: .ï¼?
FROM python:3.12-slim

ENV LANGGRAPH_STRICT_MSGPACK=true

WORKDIR /app

# å®‰è?ç³»ç?ä¾è?ï¼ˆchromadb ?€è¦?g++ ç¼–è? hnswlibï¼?
RUN apt-get update && apt-get install -y --no-install-recommends \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# å®‰è? Python ä¾è?ï¼ˆå?å¤åˆ¶ requirements ä»¥åˆ©??Docker å±‚ç?å­˜ï?
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# å¤åˆ¶?ç«¯ä»???Œå…±äº«æ¨¡??
COPY backend/ ./backend/
COPY opc_service/ ./opc_service/

# ?åŠ¡ç«¯å£
EXPOSE 8000

# ?¥åº·æ£€??
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# ?¯åŠ¨ FastAPI
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
