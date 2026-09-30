# EvoLoop OPC Service ??Dockerfile
# ?ºä? Python 3.12ï¼Œè?è¡?OPC UA å·¥ä??°æ®å¾®æ???
# ?„å»ºä¸Šä??‡ï?é¡¹ç›®?¹ç›®å½•ï?docker-compose ä¸­æ?å®?context: .ï¼?
FROM python:3.12-slim

ENV LANGGRAPH_STRICT_MSGPACK=true

WORKDIR /app

# å®‰è? Python ä¾è?ï¼ˆå?å¤åˆ¶ requirements ä»¥åˆ©??Docker å±‚ç?å­˜ï?
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# å¤åˆ¶ OPC ?åŠ¡ä»??
COPY opc_service/ ./opc_service/

# ?åŠ¡ç«¯å£
EXPOSE 8001

# ?¥åº·æ£€??
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/opc/health')" || exit 1

# ?¯åŠ¨ FastAPI
CMD ["uvicorn", "opc_service.main:app", "--host", "0.0.0.0", "--port", "8001"]
