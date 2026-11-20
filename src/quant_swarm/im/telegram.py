"""Telegram gateway — long-poll bridge between a bot and qs.chat.*.

Inbound : TG text message -> ChatMessage(channel=telegram,
          session_id="tg-<chat_id>") -> qs.chat.in
Outbound: qs.chat.out.telegram -> sendMessage back to the chat the
          session came from.

Long polling works from behind NAT — no public endpoint needed. The
token is read from the env var named by ``token_env`` (default
``QS_TG_TOKEN``); without it the gateway idles instead of crash-looping
under the supervisor.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
from loguru import logger

from quant_swarm.agents.base import AgentBase
from quant_swarm.core import subjects
from quant_swarm.core.bus.base import BusMessage
from quant_swarm.core.schemas import ChatChannel, ChatMessage, ChatRole

_API = "https://api.telegram.org"


def _lookup_token(var: str) -> str:
    """Same .env fallback as core.llm — QS_* vars bind, but a bare
    ``QS_TG_TOKEN`` in .env is still the simplest place to keep it."""
    tok = os.environ.get(var, "")
    if tok:
        return tok
    from pathlib import Path

    env_file = Path(".env")
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(f"{var}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


class TelegramClient:
    """Minimal Bot API wrapper — getUpdates + sendMessage."""

    def __init__(self, token: str) -> None:
        self._http = httpx.AsyncClient(
            base_url=f"{_API}/bot{token}", timeout=httpx.Timeout(45.0, connect=10.0)
        )

    async def get_updates(self, offset: int, poll_timeout: int = 30) -> list[dict]:
        resp = await self._http.get(
            "/getUpdates",
            params={
                "offset": offset,
                "timeout": poll_timeout,
                "allowed_updates": '["message"]',
            },
        )
        resp.raise_for_status()
        return resp.json().get("result", [])

    async def send(self, chat_id: int | str, text: str) -> None:
        # Telegram caps messages at 4096 chars — chunk long replies.
        for i in range(0, max(len(text), 1), 4090):
            await self._http.post(
                "/sendMessage",
                json={"chat_id": chat_id, "text": text[i : i + 4090] or "…"},
            )

    async def send_chat_action(self, chat_id: int | str, action: str = "typing") -> None:
        try:
            await self._http.post(
                "/sendChatAction", json={"chat_id": chat_id, "action": action}
            )
        except Exception:
            pass

    async def close(self) -> None:
        await self._http.aclose()


class TelegramGateway(AgentBase):
    name = "im_telegram"

    def __init__(self, *args, client: Any | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._client = client
        self._offset = 0
        self._poll_task: asyncio.Task | None = None
        self._busy: dict[str, asyncio.Task] = {}  # session -> typing keepalive

    async def on_start(self) -> None:
        if self._client is None:
            token_env = self.spec.params.get("token_env", "QS_TG_TOKEN")
            token = _lookup_token(token_env)
            if not token:
                logger.warning(
                    "im_telegram: no token (set {} in .env) — idling", token_env
                )
                return
            self._client = TelegramClient(token)
        await self.subscribe(subjects.chat_out(ChatChannel.TELEGRAM), self._on_reply)
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("im_telegram ready (long-poll)")

    async def on_stop(self) -> None:
        if self._poll_task:
            self._poll_task.cancel()
        for t in self._busy.values():
            t.cancel()
        if hasattr(self._client, "close"):
            await self._client.close()

    # -- inbound ----------------------------------------------------------
    async def _poll_loop(self) -> None:
        timeout = int(self.spec.params.get("poll_timeout", 30))
        while True:
            try:
                updates = await self._client.get_updates(self._offset, timeout)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("getUpdates failed: {} — retry in 5s", exc)
                await asyncio.sleep(5)
                continue
            for upd in updates:
                self._offset = max(self._offset, upd["update_id"] + 1)
                await self._handle_update(upd)
            # fast/fake clients can return instantly — never starve the loop
            await asyncio.sleep(0)

    async def _handle_update(self, upd: dict) -> None:
        msg = upd.get("message") or {}
        text = (msg.get("text") or "").strip()
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        if not text or chat_id is None:
            return
        session = f"tg-{chat_id}"
        self._start_typing(session, chat_id)
        await self.bus.publish_model(
            subjects.CHAT_IN,
            ChatMessage(
                session_id=session,
                role=ChatRole.USER,
                channel=ChatChannel.TELEGRAM,
                content=text,
            ),
        )
        self.bump("inbound")

    def _start_typing(self, session: str, chat_id: int) -> None:
        """Keep the 'typing…' indicator alive while experts think (it
        expires client-side after ~5s, so re-send periodically)."""
        old = self._busy.pop(session, None)
        if old:
            old.cancel()

        async def loop() -> None:
            while True:
                await self._client.send_chat_action(chat_id)
                await asyncio.sleep(4)

        self._busy[session] = asyncio.create_task(loop())

    # -- outbound ---------------------------------------------------------
    async def _on_reply(self, msg: BusMessage) -> None:
        chat_msg = msg.envelope().unwrap(ChatMessage)
        session = chat_msg.session_id
        if not session.startswith("tg-"):
            return
        chat_id: int | str = session[3:]
        try:
            chat_id = int(chat_id)
        except ValueError:
            pass
        task = self._busy.pop(session, None)
        if task:
            task.cancel()
        header = f"【{chat_msg.expert}】\n" if chat_msg.expert else ""
        try:
            await self._client.send(chat_id, header + chat_msg.content)
            self.bump("outbound")
        except Exception as exc:
            logger.warning("sendMessage failed: {}", exc)
