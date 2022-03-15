from __future__ import annotations

from .rtfm import RTFM
from core import Parrot


async def setup(bot: Parrot):
    await bot.add_cog(RTFM(bot))
