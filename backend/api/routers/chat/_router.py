"""chat 路由共用同一個 APIRouter；各子模組以 decorator 註冊端點。"""

from fastapi import APIRouter

router = APIRouter(tags=["chat"])
