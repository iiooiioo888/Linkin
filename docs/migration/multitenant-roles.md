# 多租戶角色目錄遷移（2026-10-15）

## 變更摘要

- 角色目錄由單一 `backend/data/role_catalog.json` 改為 **每帳戶一檔**：
  `backend/data/role_catalog/<user_id>.json`（可用 `EVOL_ROLE_CATALOG_DIR` 覆寫目錄）。
- 內建 `STANDARD_ROLES` 與 `backend/linkin/roles.py` 種子 **僅為模板**；執行期只讀當前租戶的 clone。
- 任務、角色記憶、監控偏好、技能覆寫、席位軌跡與計費上下文皆帶 **租戶 user_id**。

## 既有資料

1. 若仍存在 `backend/data/role_catalog.json` 且未設定 `EVOL_ROLE_CATALOG_PATH`：
   - 首次啟動時自動複製至 `backend/data/role_catalog/deploy_admin.json`。
   - 該檔擁有者為部署管理員帳戶（gate 登入使用者名稱需與 `deploy_admin` 對齊，或手動將檔更名為你的 gate 使用者 ID）。
2. 無 `user_id` 的舊任務：僅對租戶 `deploy_admin` 與測試預設 `dev` 可見；新建任務一律寫入當前租戶。

## 操作建議

- 新帳戶首次使用監控中心前，可執行 `python -m backend.scripts.seed_linkin_world`（以該帳戶登入後）寫入靈境 16 席 clone。
- 測試隔離仍可使用 `EVOL_ROLE_CATALOG_PATH` 指向單一 JSON（所有租戶共用該檔，僅供 pytest）。

## 驗收

見 `backend/tests/test_multitenant_roles.py` 與 PR 說明中的隔離清單。
