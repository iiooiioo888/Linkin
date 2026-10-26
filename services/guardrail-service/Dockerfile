FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir fastapi uvicorn pydantic
COPY linkin_core /app/linkin_core
COPY services/guardrail-service /app/svc
ENV PYTHONPATH=/app/svc:/app
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
