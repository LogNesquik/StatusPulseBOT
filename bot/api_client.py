import os
import httpx


class StatusPulseAPI:
    def __init__(self):
        self.base_url = os.getenv("API_INTERNAL_URL", "http://api:8000").rstrip("/")
        self.token = os.getenv("BOT_INTERNAL_TOKEN", "")
        self.timeout = httpx.Timeout(8.0)

    def _headers(self):
        return {"X-Bot-Token": self.token}

    async def link(self, code: str, chat_id: int):
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.post("/api/v1/telegram/bot/link/", json={"code": code, "chat_id": chat_id}, headers=self._headers())
            response.raise_for_status()
            return response.json()

    async def monitors(self, chat_id: int):
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.get("/api/v1/telegram/bot/monitors/", params={"chat_id": chat_id}, headers=self._headers())
            response.raise_for_status()
            return response.json()

    async def incidents(self, chat_id: int):
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.get("/api/v1/telegram/bot/incidents/", params={"chat_id": chat_id}, headers=self._headers())
            response.raise_for_status()
            return response.json()
