import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any

from discord import Client, Intents, Message, MessageType
from discord.utils import MISSING
from expression.collections import Block
from lagom import Container, Singleton
from lagom.environment import Env

logger: logging.Logger = logging.getLogger(__name__)


class MyDiscordClientEnvironment(Env):
    discord_token: str


class MessageHandler(ABC):
    """메시지 이벤트 핸들러의 abstract class입니다."""

    @staticmethod
    @abstractmethod
    async def handle(message: Message) -> None:
        raise NotImplementedError()


class ReplyDeletion(MessageHandler):
    """메시지 이벤트를 이용하여 답장을 삭제하는 메시지 핸들러입니다."""

    @staticmethod
    async def handle(message: Message) -> None:
        """전달된 메시지가 답장 기능을 사용하였을 경우 삭제한 후 경고 메시지를
        전송합니다.

        Args:
            message (Message): 주입받은 메시지 객체
        """
        match message.type:
            case MessageType.reply:
                logger.info(
                    f"{message.author.name}@{message.channel.name}: {message.content}"
                )
                await message.delete()
                await message.channel.send(
                    "저희 서버에서 답장 기능은 금지되어 있어요! <#687619273849438228> 정독 부탁드려요!"
                )
            case _:
                pass


class MessageHandlerList(Block[MessageHandler]):
    """메시지 핸들러를 모아둔 immutable collection입니다."""


class MyDiscordClient(Client):
    """디스코드 봇 클라이언트 클래스입니다."""

    _discord_token: str
    _message_handler_list: MessageHandlerList

    def __init__(
        self,
        env: MyDiscordClientEnvironment,
        message_handler_list: MessageHandlerList,
        *,
        intents: Intents,
        **options: Any,
    ) -> None:
        super().__init__(intents=intents, **options)
        self._discord_token = env.discord_token
        self._message_handler_list = message_handler_list

    def run(
        self,
        *,
        reconnect: bool = True,
        log_handler: logging.Handler = MISSING,
        log_formatter: logging.Formatter = MISSING,
        log_level: int = MISSING,
        root_logger: bool = MISSING,
    ) -> None:
        super().run(
            token=self._discord_token,
            reconnect=reconnect,
            log_handler=log_handler,
            log_formatter=log_formatter,
            log_level=log_level,
            root_logger=root_logger,
        )

    async def on_message(self, message: Message) -> None:
        """메시지 전송 이벤트가 발생할 시, 메시지 이벤트 핸들러들을 처리합니다.

        메시지 이벤트 시 실행되는 이벤트 핸들러입니다. 클래스 생성 시 주입받은 메시지
        핸들러들을 비동기적으로 실행합니다.

        Args:
            message (Message): 주입받은 메시지 객체
        """
        await asyncio.gather(
            *(x.handle(message=message) for x in self._message_handler_list)
        )


def bootstrap() -> Container:
    container = Container()
    container[Intents] = Intents.default() | Intents(message_content=True)
    container[MyDiscordClientEnvironment] = Singleton(MyDiscordClientEnvironment)
    container[MessageHandlerList] = MessageHandlerList.empty().cons(ReplyDeletion())
    container[MyDiscordClient] = Singleton(MyDiscordClient)
    return container
