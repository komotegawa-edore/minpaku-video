from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

from minpaku_video.config import get_settings
from minpaku_video.models.project import CostEntry

logger = logging.getLogger(__name__)

# Claude pricing (per million tokens)
_PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-20250514": (3.0, 15.0),
    "claude-haiku-4-20250514": (0.80, 4.0),
}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    input_price, output_price = _PRICING.get(model, (3.0, 15.0))
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000


class ClaudeClient:
    def __init__(self) -> None:
        settings = get_settings()
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.claude_model
        self._max_tokens = settings.claude_max_tokens

    async def generate(
        self,
        system: str,
        user_message: str,
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> tuple[str, CostEntry]:
        model = model or self._model
        max_tokens = max_tokens or self._max_tokens

        response = await self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )

        text = response.content[0].text
        usage = response.usage
        cost = _estimate_cost(model, usage.input_tokens, usage.output_tokens)

        cost_entry = CostEntry(
            stage="generate",
            model=model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=cost,
        )

        logger.info(
            f"Claude API: 入力{usage.input_tokens}/出力{usage.output_tokens}トークン, ${cost:.4f}"
        )

        return text, cost_entry

    async def generate_with_image(
        self,
        system: str,
        user_message: str,
        image_data: str,
        image_media_type: str = "image/png",
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> tuple[str, CostEntry]:
        """画像付きメッセージを送信する (Vision)。"""
        model = model or self._model
        max_tokens = max_tokens or self._max_tokens

        response = await self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": image_media_type,
                            "data": image_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": user_message,
                    },
                ],
            }],
        )

        text = response.content[0].text
        usage = response.usage
        cost = _estimate_cost(model, usage.input_tokens, usage.output_tokens)

        cost_entry = CostEntry(
            stage="script",
            model=model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=cost,
        )

        logger.info(
            f"Claude Vision API: 入力{usage.input_tokens}/出力{usage.output_tokens}トークン, ${cost:.4f}"
        )

        return text, cost_entry

    async def generate_json(
        self,
        system: str,
        user_message: str,
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> tuple[Any, CostEntry]:
        text, cost_entry = await self.generate(
            system,
            user_message,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        try:
            data = _parse_json(text)
        except json.JSONDecodeError:
            logger.warning("JSONパース失敗、リトライ")
            retry_msg = (
                f"{user_message}\n\n"
                "重要: 必ず有効なJSONのみを出力してください。"
                "コードブロックやマークダウンは不要です。"
            )
            text, retry_cost = await self.generate(
                system,
                retry_msg,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            cost_entry.input_tokens += retry_cost.input_tokens
            cost_entry.output_tokens += retry_cost.output_tokens
            cost_entry.cost_usd += retry_cost.cost_usd
            data = _parse_json(text)

        return data, cost_entry

    async def close(self) -> None:
        await self._client.close()


def _parse_json(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return json.loads(text)
