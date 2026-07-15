from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, cast

from aiohttp import ClientError, ClientTimeout
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods.base import TelegramType

if TYPE_CHECKING:
    from aiogram.client.bot import Bot
    from aiogram.methods import TelegramMethod


class HttpProxyTelegramSession(AiohttpSession):
    """Route Bot API requests through a standard HTTP(S) forward proxy."""

    def __init__(self, proxy_url: str) -> None:
        super().__init__()
        self._proxy_url = proxy_url

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[TelegramType],
        timeout: int | None = None,
    ) -> TelegramType:
        session = await self.create_session()
        url = self.api.api_url(token=bot.token, method=method.__api_method__)
        form = self.build_form_data(bot=bot, method=method)
        request_timeout = self.timeout if timeout is None else timeout

        try:
            async with session.post(
                url,
                data=form,
                proxy=self._proxy_url,
                timeout=ClientTimeout(total=request_timeout),
            ) as response:
                raw_result = await response.text()
        except asyncio.TimeoutError as exc:
            raise TelegramNetworkError(
                method=method, message="Request timeout error"
            ) from exc
        except ClientError as exc:
            raise TelegramNetworkError(
                method=method, message=f"{type(exc).__name__}: {exc}"
            ) from exc

        result = self.check_response(
            bot=bot,
            method=method,
            status_code=response.status,
            content=raw_result,
        )
        return cast(TelegramType, result.result)
