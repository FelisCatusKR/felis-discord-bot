import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from discord import Client, Intents, Message, MessageType
from discord.utils import MISSING
from expression.collections import Block
from lagom import Container, Singleton
from lagom.environment import Env
from returns.context import ReaderFutureResult, ReaderIOResult
from returns.converters import maybe_to_result
from returns.future import Future, FutureResult
from returns.io import IO, IOResult, IOSuccess
from returns.maybe import Maybe, Nothing, Some

logger: logging.Logger = logging.getLogger(__name__)


class MyDiscordClientEnvironment(Env):
    discord_token: str


class _DbConnection(Protocol):
    session: str


@dataclass(frozen=True)
class Deletion:
    server_id: int
    template_message: str | None


_repo: list[Deletion] = [
    Deletion(
        server_id=669234451263389696,
        template_message="저희 서버에서 답장 기능은 금지되어 있어요! <#687619273849438228> 정독 부탁드려요!",
    ),
    Deletion(server_id=910708305247211520, template_message="야호"),
]


class DeletionRepo:
    @staticmethod
    def get_all() -> ReaderIOResult[list[Deletion], None, _DbConnection]:
        def func(conn: _DbConnection) -> IOResult[list[Deletion], None]:
            logger.debug(conn)
            return IOSuccess.from_value(_repo)

        return ReaderIOResult(func)


_MessageHandler = Callable[[Message], ReaderFutureResult[None, Any, _DbConnection]]


def delete_reply(
    message: Message,
) -> ReaderFutureResult[None, None, _DbConnection]:
    """전달된 메시지가 답장 기능을 사용하였을 경우 삭제한 후 경고 메시지를
    전송합니다.

    Args:
        message (Message): 주입받은 메시지 객체
    """

    def func(dep: _DbConnection) -> FutureResult[None, None]:
        deletions: IO[list[Deletion]] = DeletionRepo.get_all()(dep).value_or([])
        m: Maybe[Message] = _validate_if_message_type_is_reply(message).bind(
            _validate_if_message_is_from_deletions(deletions)
        )
        return FutureResult.from_result(maybe_to_result(m)).bind_awaitable(
            _delete_message_and_send_alert(deletions)
        )

    return ReaderFutureResult(func)


def _validate_if_message_type_is_reply(message: Message) -> Maybe[Message]:
    match message.type:
        case MessageType.reply:
            logger.info(
                f"{message.author.name}@{message.channel.name}: {message.content}"
            )
            return Some(message)
        case _:
            return Nothing


def _validate_if_message_is_from_deletions(deletions: IO[list[Deletion]]):
    def func(message: Message) -> Maybe[Message]:
        result: IO[Deletion | None] = deletions.map(
            lambda c: filter(lambda x: x.server_id == message.guild.id, c)
        ).map(lambda filtered_deletions: next(filtered_deletions, None))
        if result:
            return Some(message)
        else:
            return Nothing

    return func


def _delete_message_and_send_alert(deletions: IO[list[Deletion]]):
    async def func(message: Maybe[Message]):
        deletion: IO[Deletion] = deletions.map(
            lambda l: filter(lambda x: x.server_id == message.guild.id, l)
        ).map(lambda l: next(l))
        await message.delete()
        return await (
            Future.from_io(deletion)
            .bind_awaitable(lambda x: message.channel.send(x.template_message))
            .awaitable()
        )

    return func


MessageHandlerList = Block[_MessageHandler]


@dataclass(frozen=True)
class Test:
    session: str


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
            *(
                handler(message=message)(Test(session="test")).awaitable()
                for handler in self._message_handler_list
            )
        )


def bootstrap() -> Container:
    container = Container()
    container[Intents] = Intents.default() | Intents(message_content=True)
    container[MyDiscordClientEnvironment] = Singleton(MyDiscordClientEnvironment)
    container[MessageHandlerList] = Block.empty().cons(delete_reply)
    container[MyDiscordClient] = Singleton(MyDiscordClient)
    return container
