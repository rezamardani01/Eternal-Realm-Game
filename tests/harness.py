"""Drive the real dispatcher with raw Bale updates and a fake HTTP session."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from baleropy import Bot
from baleropy.client.session.base import BaseSession

from eternal_realm.bot.app import build_dispatcher
from eternal_realm.bot.services import Services


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.chat_admins: set[int] = set()
        self._next_id = 1000

    async def _send(self, bot: Any, method: Any) -> tuple[int, bytes]:
        name = method.__api_method__
        payload = json.loads(method.model_dump_json(exclude_none=True, by_alias=True))
        self.calls.append((name, payload))
        if name == "getMe":
            result: Any = {"id": 1, "is_bot": True, "first_name": "bot", "username": "er_bot"}
        elif name == "getChatMember":
            uid = int(payload["user_id"])
            result = {
                "status": "administrator" if uid in self.chat_admins else "member",
                "user": {"id": uid, "is_bot": False, "first_name": f"user{uid}"},
            }
        elif name.startswith(("send", "edit", "forward")) and name != "sendChatAction":
            self._next_id += 1
            result = {
                "message_id": self._next_id,
                "date": 0,
                "chat": {"id": payload.get("chat_id", 0), "type": "private"},
                "text": payload.get("text", ""),
            }
        else:
            result = True
        return 200, json.dumps({"ok": True, "result": result}).encode()

    def stream_content(self, url: str, chunk_size: int = 65536) -> AsyncIterator[bytes]:
        raise NotImplementedError

    async def close(self) -> None:
        return None

    # --- inspection helpers ---------------------------------------------------------------
    def sent(self, method: str = "sendMessage") -> list[dict[str, Any]]:
        return [p for n, p in self.calls if n == method]

    def texts(self) -> list[str]:
        return [p.get("text", "") for n, p in self.calls if n in ("sendMessage", "editMessageText")]

    def last_text(self) -> str:
        return self.texts()[-1]

    def last_buttons(self) -> list[dict[str, Any]]:
        for name, payload in reversed(self.calls):
            if name in ("sendMessage", "editMessageText") and "reply_markup" in payload:
                return [b for row in payload["reply_markup"]["inline_keyboard"] for b in row]
        return []

    def callback_answers(self) -> list[dict[str, Any]]:
        return self.sent("answerCallbackQuery")

    def reset(self) -> None:
        self.calls.clear()


class Harness:
    def __init__(self, services: Services) -> None:
        self.services = services
        services.bot_username = "er_bot"
        services.throttle.user_gap = 0
        services.throttle.group_max = 10_000
        self.session = FakeSession()
        self.bot = Bot("123456:TESTTOKEN", session=self.session)
        self.dp = build_dispatcher(services)
        self._update_id = 0
        self._message_id = 0

    def _user(self, uid: int, username: str | None = None) -> dict[str, Any]:
        return {"id": uid, "is_bot": False, "first_name": f"user{uid}", "username": username or f"u{uid}"}

    async def say(
        self,
        uid: int,
        text: str,
        *,
        chat: int | None = None,
        group: bool = False,
        reply_to: dict[str, Any] | None = None,
    ) -> None:
        self._update_id += 1
        self._message_id += 1
        chat_id = chat if chat is not None else (-500 if group else uid)
        message: dict[str, Any] = {
            "message_id": self._message_id,
            "from": self._user(uid),
            "chat": {"id": chat_id, "type": "group" if group else "private", "title": "گروه تست"},
            "date": 0,
            "text": text,
        }
        if reply_to is not None:
            message["reply_to_message"] = reply_to
        await self.dp.feed_raw_update(
            self.bot, {"update_id": self._update_id, "message": message}
        )

    def message_of(self, uid: int, *, group: bool = True, message_id: int = 7) -> dict[str, Any]:
        """A message authored by ``uid``, to be used as the target of a reply."""
        return {
            "message_id": message_id,
            "from": self._user(uid),
            "chat": {"id": -500 if group else uid, "type": "group" if group else "private"},
            "date": 0,
            "text": "سلام",
        }

    async def click(
        self, uid: int, data: str, *, group: bool = False, message_id: int = 555, chat: int | None = None
    ) -> None:
        self._update_id += 1
        chat_id = chat if chat is not None else (-500 if group else uid)
        await self.dp.feed_raw_update(
            self.bot,
            {
                "update_id": self._update_id,
                "callback_query": {
                    "id": f"cb{self._update_id}",
                    "from": self._user(uid),
                    "data": data,
                    "message": {
                        "message_id": message_id,
                        "chat": {"id": chat_id, "type": "group" if group else "private"},
                        "date": 0,
                        "text": "x",
                    },
                },
            },
        )

    def button_data(self, label_part: str) -> str:
        for button in self.session.last_buttons():
            if label_part in button["text"]:
                return button["callback_data"]
        raise AssertionError(f"no button containing {label_part!r}: {self.session.last_buttons()}")
