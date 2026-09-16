# Linkin 任務 Runner 映像（可選）

MVP 預設使用上游白名單映像：`python:3.12-slim`、`node:20-slim`、`alpine:3.20`。

若要加入自訂 runner，在此目錄新增 Dockerfile 並將 `linkin/runner-<name>:<tag>` 加入環境變數 `EVOL_EPHEMERAL_IMAGE_ALLOWLIST`。
