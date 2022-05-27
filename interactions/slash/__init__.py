from __future__ import annotations
from typing import Literal, Optional

from core import Cog, Parrot, Context

from discord.ext import commands
from discord import app_commands
import discord


class ContextMenu(Cog):
    def __init__(self, bot: Parrot):
        self.bot = bot

        self.ctx_menu = app_commands.ContextMenu(
            name="Interpret as command",
            # description="Interpret the message as a command.",
            guild_ids=[978694756022489098],
            callback=self.ctx_menu
        )
        self.bot.tree.add_command(self.ctx_menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.ctx_menu)

    async def ctx_menu(self, interaction: discord.Interaction, message: discord.Message) -> None:
        await interaction.response.defer(thinking=True)
        prefix = await self.bot.get_guild_prefixes(message.guild)
        if prefix is not None and not message.content.startswith(prefix):
            message.content = f"{prefix}{message.content}"
            await self.bot.process_commands(message)
            return
        return await interaction.response.send_message(
            f"{message.author.mention} the command is already interpreted as command. Do you think it's an error? Please report it.", ephemeral=True
        )

    @commands.command(hidden=True)
    @commands.is_owner()
    async def sync(self, ctx: Context, guilds: commands.Greedy[discord.Object], spec: Optional[Literal["~", "*"]] = None) -> None:
        if not guilds:
            if spec == "~":
                fmt = await ctx.bot.tree.sync(guild=ctx.guild)
            elif spec == "*":
                ctx.bot.tree.copy_global_to(guild=ctx.guild)
                fmt = await ctx.bot.tree.sync(guild=ctx.guild)
            else:
                fmt = await ctx.bot.tree.sync()

            await ctx.send(
                f"{ctx.author.mention} \N{SATELLITE ANTENNA} Synced {len(fmt)} commands {'globally' if spec is None else 'to the current guild.'}"
            )
            return

        fmt = 0
        for guild in guilds:
            try:
                await ctx.bot.tree.sync(guild=guild)
            except discord.HTTPException:
                pass
            else:
                fmt += 1

        await ctx.send(f"{ctx.author.mention} \N{SATELLITE ANTENNA} Synced the tree to {fmt}/{len(guilds)} guilds.")


async def setup(bot: Parrot) -> None:
    await bot.add_cog(ContextMenu(bot))