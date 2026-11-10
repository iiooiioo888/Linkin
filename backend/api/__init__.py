"""REST API 層（自 backend.main 抽出的路由與模型）。

入口：`backend.main` 只負責組裝 app（lifespan／middleware／例外處理／include_router），
各領域端點集中在 `backend.api.routers`。這樣 main 不再同時是應用入口與巨型路由檔。
"""
