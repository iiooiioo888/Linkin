#!/usr/bin/env bash
# 將專案目錄從活躍儲存遷移到歸檔根目錄（人工／排程用；MVP 不自動執行）。
# 用法：
#   STORAGE_BASE=/mnt/ai-media ARCHIVE_BASE=/mnt/ai-media-archive \
#     ./scripts/archive_project.sh <project_id>
set -euo pipefail

PROJECT_ID="${1:-}"
if [[ -z "$PROJECT_ID" ]]; then
  echo "用法: $0 <project_id>" >&2
  exit 1
fi

STORAGE_BASE="${STORAGE_BASE:-${LVS_STORAGE_BASE:-/mnt/ai-media}}"
ARCHIVE_BASE="${ARCHIVE_BASE:-${LVS_ARCHIVE_BASE:-/mnt/ai-media-archive}}"

SRC="${STORAGE_BASE}/projects/${PROJECT_ID}"
DST="${ARCHIVE_BASE}/projects/${PROJECT_ID}"

if [[ ! -d "$SRC" ]]; then
  echo "來源不存在: $SRC" >&2
  exit 1
fi

mkdir -p "$(dirname "$DST")"
if [[ -e "$DST" ]]; then
  echo "目標已存在: $DST" >&2
  exit 1
fi

echo "歸檔 $SRC → $DST"
mv "$SRC" "$DST"
echo "完成。請在 Studio 將專案 status 設為 archived。"
