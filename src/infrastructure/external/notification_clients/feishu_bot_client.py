"""
飞书群机器人通知客户端
"""
import asyncio
import base64
import hashlib
import hmac
import time
from typing import Dict, Optional

import requests

from .base import NotificationClient


class FeishuBotClient(NotificationClient):
    """飞书群自定义机器人通知客户端"""

    channel_key = "feishu"
    display_name = "飞书"

    def __init__(
        self,
        bot_url: Optional[str] = None,
        bot_secret: Optional[str] = None,
        pcurl_to_mobile: bool = True,
    ):
        super().__init__(enabled=bool(bot_url), pcurl_to_mobile=pcurl_to_mobile)
        self.bot_url = bot_url
        self.bot_secret = bot_secret

    def _build_sign(self, timestamp: str) -> str:
        """Feishu bot signature: HMAC-SHA256 with "timestamp\\nsecret" as key, empty body."""
        string_to_sign = f"{timestamp}\n{self.bot_secret}"
        digest = hmac.new(
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        return base64.b64encode(digest).decode("utf-8")

    async def send(self, product_data: Dict, reason: str) -> None:
        if not self.is_enabled():
            raise RuntimeError("飞书 未启用")

        message = self._build_message(product_data, reason)
        markdown_lines = [
            f"**价格**: {message.price}",
            f"**原因**: {message.reason}",
            "",
        ]
        if message.mobile_link:
            markdown_lines.append(f"[打开商品（手机）]({message.mobile_link})")
            markdown_lines.append(f"[打开商品（电脑）]({message.desktop_link})")
        else:
            markdown_lines.append(f"[打开商品]({message.desktop_link})")

        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": message.notification_title},
                    "template": "orange",
                },
                "elements": [
                    {"tag": "markdown", "content": "\n".join(markdown_lines)},
                ],
            },
        }
        if self.bot_secret:
            timestamp = str(int(time.time()))
            payload["timestamp"] = timestamp
            payload["sign"] = self._build_sign(timestamp)

        headers = {"Content-Type": "application/json"}
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: requests.post(
                self.bot_url,
                json=payload,
                headers=headers,
                timeout=10,
            ),
        )
        response.raise_for_status()
        result = response.json()
        code = result.get("code", result.get("StatusCode", 0))
        if code != 0:
            raise RuntimeError(result.get("msg", "飞书机器人返回未知错误"))
