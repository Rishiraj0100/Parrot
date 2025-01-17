from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any, Final, TypeVar

import discord
from core import Context, Parrot, ParrotView

if TYPE_CHECKING:
    from typing import TypeAlias

    from typing_extensions import ParamSpec

    P = ParamSpec("P")
    T = TypeVar("T")

    A = TypeVar("A", bound=bool)
    B = TypeVar("B", bound=bool)

__all__: tuple[str, ...] = (
    "DiscordColor",
    "DEFAULT_COLOR",
    "executor",
    "chunk",
    "BaseView",
    "double_wait",
    "wait_for_delete",
)

DiscordColor: TypeAlias = discord.Color | int

DEFAULT_COLOR: Final[discord.Color] = discord.Color(0x2F3136)


def chunk(iterable: list[T], *, count: int) -> list[list[T]]:
    return [iterable[i : i + count] for i in range(0, len(iterable), count)]


def executor() -> Callable[[Callable[P, T]], Callable[P, asyncio.Future[T]]]:
    def decorator(func: Callable[P, T]) -> Callable[P, asyncio.Future[T]]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs):
            partial = functools.partial(func, *args, **kwargs)
            loop = asyncio.get_event_loop()
            return loop.run_in_executor(None, partial)

        return wrapper

    return decorator


async def wait_for_delete(
    ctx: Context[Parrot],
    message: discord.Message,
    *,
    emoji: str = "\N{BLACK SQUARE FOR STOP}",
    bot: discord.Client | None = None,
    user: discord.User | discord.Member | tuple[discord.User, ...] | None = None,
    timeout: float | None = None,
) -> bool:
    if not user:
        user = ctx.author
    try:
        await message.add_reaction(emoji)
    except discord.DiscordException:
        pass

    def check(reaction: discord.Reaction, _user: discord.User) -> bool:
        if reaction.emoji == emoji and reaction.message == message:
            return _user in user if isinstance(user, tuple) else _user == user
        else:
            return False

    resolved_bot: discord.Client = bot or ctx.bot
    try:
        await resolved_bot.wait_for("reaction_add", timeout=timeout, check=check)
    except asyncio.TimeoutError:
        return False
    else:
        await message.delete()
        return True


async def double_wait(
    task1: Coroutine[Any, Any, A],
    task2: Coroutine[Any, Any, B],
    *,
    loop: asyncio.AbstractEventLoop | None = None,
) -> tuple[set[asyncio.Task[A] | asyncio.Task[B]], set[asyncio.Task[A] | asyncio.Task[B]]]:
    if not loop:
        loop = asyncio.get_event_loop()

    return await asyncio.wait(
        [
            loop.create_task(task1),
            loop.create_task(task2),
        ],
        return_when=asyncio.FIRST_COMPLETED,
    )


class BaseView(ParrotView):
    pass
