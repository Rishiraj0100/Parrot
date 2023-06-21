from __future__ import annotations

import asyncio
import io
import logging
from itertools import zip_longest
from typing import Any, Dict, Optional, Tuple, Type, Union

from motor.motor_asyncio import AsyncIOMotorCollection  # type: ignore
from pymongo import ReturnDocument  # type: ignore
from typing_extensions import Annotated

Collection = Type[AsyncIOMotorCollection]
import discord
from cogs.meta.robopage import SimplePages
from cogs.utils import method as mt
from core import Cog, Context, Parrot
from discord.ext import commands, tasks
from utilities.checks import is_mod
from utilities.converters import convert_bool
from utilities.formats import TabularData
from utilities.rankcard import rank_card
from utilities.time import FriendlyTimeResult, ShortTime, UserFriendlyTime

log = logging.getLogger("cogs.utils.utils")


class AfkFlags(commands.FlagConverter, prefix="--", delimiter=" "):
    ignore_channel: Tuple[discord.TextChannel, ...] = []
    _global: Optional[convert_bool] = commands.flag(name="global", default=False)
    _for: Optional[ShortTime] = commands.flag(name="for", default=None)
    text: Optional[str] = None
    after: Optional[ShortTime] = None


REACTION_EMOJI = ["\N{UPWARDS BLACK ARROW}", "\N{DOWNWARDS BLACK ARROW}"]


OTHER_REACTION = {
    "INVALID": {"emoji": "\N{WARNING SIGN}", "color": 0xFFFFE0},
    "ABUSE": {"emoji": "\N{DOUBLE EXCLAMATION MARK}", "color": 0xFFA500},
    "INCOMPLETE": {"emoji": "\N{WHITE QUESTION MARK ORNAMENT}", "color": 0xFFFFFF},
    "DECLINE": {"emoji": "\N{CROSS MARK}", "color": 0xFF0000},
    "APPROVED": {"emoji": "\N{WHITE HEAVY CHECK MARK}", "color": 0x90EE90},
    "DUPLICATE": {"emoji": "\N{HEAVY EXCLAMATION MARK SYMBOL}", "color": 0xDDD6D5},
}


class Utils(Cog):
    """Utilities for server, UwU"""

    def __init__(self, bot: Parrot) -> None:
        self.bot = bot
        self.collection: Collection = bot.timers
        self.lock = asyncio.Lock()
        self.message: Dict[int, Dict[str, Any]] = {}
        self.ON_TESTING = False
        self.server_stats_updater.start()

        self.create_timer = self.bot.create_timer
        self.delete_timer = self.bot.delete_timer

    @property
    def display_emoji(self) -> discord.PartialEmoji:
        return discord.PartialEmoji(name="sparkles_", id=892435276264259665)

    @commands.group(aliases=["remind", "reminder"], invoke_without_command=True)
    @Context.with_type
    async def remindme(
        self,
        ctx: Context,
        *,
        when: Annotated[
            FriendlyTimeResult, UserFriendlyTime(commands.clean_content, default="...")
        ],
    ) -> None:
        """Reminds you of something after a certain amount of time.

        The input can be any direct date (e.g. YYYY-MM-DD) or a human
        readable offset. Examples:

        - "next thursday at 3pm do something funny"
        - "do the dishes tomorrow"
        - "in 3 days do the thing"
        - "2d unmute someone"

        Times are in UTC unless a timezone is specified
        using the "timezone set" command.
        """
        if not ctx.invoked_subcommand:
            seconds = when.dt.timestamp()
            text = (
                f"{ctx.author.mention} alright, you will be mentioned in {ctx.channel.mention} at **<t:{int(seconds)}:R>**."
                f"To delete your reminder consider typing ```\n{ctx.clean_prefix}remind delete {ctx.message.id}```"
            )
            try:
                await ctx.reply(f"{ctx.author.mention} check your DM", delete_after=5)
                await ctx.author.send(
                    text,
                    view=ctx.send_view(),
                )
            except discord.Forbidden:
                await ctx.reply(text)

            await self.create_timer(
                expires_at=seconds,
                created_at=ctx.message.created_at.timestamp(),
                content=when.arg,
                message=ctx.message,
            )
            log.info(
                "Created a reminder for %s. reminder exipres at %s", ctx.author, seconds
            )

    @remindme.command(name="list", aliases=["all"])
    @Context.with_type
    async def _list(self, ctx: Context) -> None:
        """To get all your reminders of first 10 active reminders"""
        ls = []
        log.info("Fetching reminders for %s from database.", ctx.author)
        async for data in self.collection.find({"messageAuthor": ctx.author.id}):
            guild = self.bot.get_guild(data.get("guild", 0))
            ls.append(
                f"<t:{int(data['expires_at'])}:R> - Where To? {guild.name if guild else 'Failed to get Guild Name'}\n"
                f"> [{data['content']}]({data['messageURL']})"
            )
            if len(ls) == 10:
                break
        if not ls:
            await ctx.send(f"{ctx.author.mention} you don't have any reminders")
            return
        p = SimplePages(ls, ctx=ctx, per_page=4)
        await p.start()

    @remindme.command(name="del", aliases=["delete", "remove"])
    @Context.with_type
    async def delremind(self, ctx: Context, message: int) -> None:
        """To delete the reminder"""
        log.info("Deleting reminder of message id %s", message)
        delete_result = await self.delete_timer(_id=message)
        if self.bot._current_timer and self.bot._current_timer["_id"] == message:
            self.bot.timer_task.cancel()
            self.bot.timer_task = self.bot.loop.create_task(self.bot.dispatch_timers())
        if delete_result.deleted_count == 0:
            await ctx.reply(
                f"{ctx.author.mention} failed to delete reminder of ID: **{message}**"
            )
        else:
            await ctx.reply(
                f"{ctx.author.mention} deleted reminder of ID: **{message}**"
            )

    @remindme.command(name="dm")
    @Context.with_type
    async def remindmedm(
        self,
        ctx: Context,
        *,
        when: Annotated[
            FriendlyTimeResult, UserFriendlyTime(commands.clean_content, default="...")
        ],
    ) -> None:
        """Same as remindme, but you will be mentioned in DM. Make sure you have DM open for the bot"""
        seconds = when.dt.timestamp()
        text = (
            f"{ctx.author.mention} alright, you will be mentioned in your DM (Make sure you have your DM open for this bot) "
            f"within **<t:{int(seconds)}:R>**. To delete your reminder consider typing ```\n{ctx.clean_prefix}remind delete {ctx.message.id}```"
        )
        try:
            await ctx.reply(f"{ctx.author.mention} check your DM", delete_after=5)
            await ctx.author.send(
                text,
                view=ctx.send_view(),
            )
        except discord.Forbidden:
            await ctx.reply(text)

        await self.create_timer(
            expires_at=seconds,
            created_at=ctx.message.created_at.timestamp(),
            content=when.arg,
            message=ctx.message,
            dm_notify=True,
        )
        log.info(
            "Created a reminder for %s. reminder exipres at %s", ctx.author, seconds
        )

    @remindme.command(name="loop", aliases=["repeat"])
    @Context.with_type
    async def remindmeloop(
        self,
        ctx: Context,
        *,
        when: Annotated[
            FriendlyTimeResult, UserFriendlyTime(commands.clean_content, default="...")
        ],
    ):
        """Same as remind me but you will get reminder on every given time.

        `$remind loop 1d To vote the bot`
        This will make a reminder for everyday `To vote the bot`
        """
        seconds = when.dt.timestamp()
        now = discord.utils.utcnow().timestamp()
        if seconds - now <= 300:
            return await ctx.reply(
                f"{ctx.author.mention} You can't set reminder for less than 5 minutes"
            )

        post = {
            "_id": ctx.message.id,
            "expires_at": seconds,
            "created_at": ctx.message.created_at.timestamp(),
            "content": when.arg,
            "embed": None,
            "messageURL": ctx.message.jump_url,
            "messageAuthor": ctx.message.author.id,
            "messageChannel": ctx.message.channel.id,
            "dm_notify": True,
            "is_todo": False,
            "mod_action": None,
            "cmd_exec_str": None,
            "extra": {"name": "SET_TIMER_LOOP", "main": {"age": str(when)}},
        }
        await self.bot.create_timer(**post)
        log.info(
            "Created a loop reminder for %s. reminder exipres at %s",
            ctx.author,
            seconds,
        )
        text = (
            f"{ctx.author.mention} Alright, you will be mentioned in your DM (Make sure you have your DM open for this bot) "
            f"within **<t:{int(seconds)}:R>**. To delete your reminder consider typing ```\n{ctx.clean_prefix}remind delete {ctx.message.id}```"
        )
        try:
            await ctx.reply(f"{ctx.author.mention} check your DM", delete_after=5)
            await ctx.author.send(
                text,
                view=ctx.send_view(),
            )
        except discord.Forbidden:
            await ctx.reply(text)

    @commands.group(invoke_without_command=True)
    @commands.bot_has_permissions(embed_links=True)
    async def tag(self, ctx: Context, *, tag: str = None):
        """Tag management, or to show the tag"""
        if not ctx.invoked_subcommand and tag is not None:
            await mt._show_tag(
                self.bot,
                ctx,
                tag,
                ctx.message.reference.resolved if ctx.message.reference else None,
            )

    @tag.command(name="create", aliases=["add"])
    @commands.bot_has_permissions(embed_links=True)
    async def tag_create(self, ctx: Context, tag: str, *, text: str):
        """To create tag. All tag have unique name"""
        await mt._create_tag(self.bot, ctx, tag, text)

    @tag.command(name="delete", aliases=["del"])
    @commands.bot_has_permissions(embed_links=True)
    async def tag_delete(self, ctx: Context, *, tag: str):
        """To delete tag. You must own the tag to delete"""
        await mt._delete_tag(self.bot, ctx, tag)

    @tag.command(name="editname")
    @commands.bot_has_permissions(embed_links=True)
    async def tag_edit_name(self, ctx: Context, tag: str, *, name: str):
        """To edit the tag name. You must own the tag to edit"""
        await mt._name_edit(self.bot, ctx, tag, name)

    @tag.command(name="edittext")
    @commands.bot_has_permissions(embed_links=True)
    async def tag_edit_text(self, ctx: Context, tag: str, *, text: str):
        """To edit the tag text. You must own the tag to edit"""
        await mt._text_edit(self.bot, ctx, tag, text)

    @tag.command(name="owner", aliases=["info"])
    @commands.bot_has_permissions(embed_links=True)
    async def tag_owner(self, ctx: Context, *, tag: str):
        """To check the tag details."""
        await mt._view_tag(self.bot, ctx, tag)

    @tag.command(name="snipe", aliases=["steal", "claim"])
    @commands.bot_has_permissions(embed_links=True)
    async def tag_claim(self, ctx: Context, *, tag: str):
        """To claim the ownership of the tag, if the owner of the tag left the server"""
        await mt._claim_owner(self.bot, ctx, tag)

    @tag.command(name="togglensfw", aliases=["nsfw", "tnsfw"])
    @commands.bot_has_permissions(embed_links=True)
    async def toggle_nsfw(self, ctx: Context, *, tag: str):
        """To enable/disable the NSFW of a Tag."""
        await mt._toggle_nsfw(self.bot, ctx, tag)

    @tag.command(name="give", aliases=["transfer"])
    @commands.bot_has_permissions(embed_links=True)
    async def tag_tranfer(self, ctx: Context, tag: str, *, member: discord.Member):
        """To transfer the ownership of tag you own to other member"""
        await mt._transfer_owner(self.bot, ctx, tag, member)

    @tag.command(name="all")
    @commands.bot_has_permissions(embed_links=True)
    async def tag_all(self, ctx: Context):
        """To show all tags"""
        await mt._show_all_tags(self.bot, ctx)

    @tag.command(name="mine")
    @commands.bot_has_permissions(embed_links=True)
    async def tag_mine(self, ctx: Context):
        """To show those tag which you own"""
        await mt._show_tag_mine(self.bot, ctx)

    @tag.command(name="raw")
    @commands.bot_has_permissions(embed_links=True)
    async def tag_raw(self, ctx: Context, *, tag: str):
        """To show the tag in raw format"""
        await mt._show_raw_tag(self.bot, ctx, tag)

    @commands.command()
    @commands.has_permissions(manage_messages=True, add_reactions=True)
    @commands.bot_has_permissions(
        embed_links=True, add_reactions=True, read_message_history=True
    )
    @Context.with_type
    async def quickpoll(self, ctx: Context, *questions_and_choices: str):
        """
        To make a quick poll for making quick decision.
        'Question must be in quotes' and 'Options' 'must' 'be' 'seperated' 'by' 'spaces'.
        Not more than 21 options. :)
        """

        def to_emoji(c) -> str:
            base = 0x1F1E6
            return chr(base + c)

        if len(questions_and_choices) < 3:
            return await ctx.send("Need at least 1 question with 2 choices.")
        if len(questions_and_choices) > 21:
            return await ctx.send("You can only have up to 20 choices.")

        question = questions_and_choices[0]
        choices = [(to_emoji(e), v) for e, v in enumerate(questions_and_choices[1:])]

        body = "\n".join(f"{key}: {c}" for key, c in choices)
        poll: discord.Message = await ctx.send(f"**Poll: {question}**\n\n{body}")
        await ctx.bulk_add_reactions(poll, *[emoji for emoji, _ in choices])

        await ctx.message.delete(delay=5)

    @commands.group(name="todo", invoke_without_command=True)
    @commands.bot_has_permissions(embed_links=True)
    async def todo(self, ctx: Context):
        """For making the TODO list"""
        if not ctx.invoked_subcommand:
            await mt._list_todo(self.bot, ctx)

    @todo.command(name="show")
    @commands.bot_has_permissions(embed_links=True)
    async def todu_show(self, ctx: Context, *, name: str):
        """To show the TODO task you created"""
        await mt._show_todo(self.bot, ctx, name)

    @todo.command(name="create")
    @commands.bot_has_permissions(embed_links=True)
    async def todo_create(self, ctx: Context, name: str, *, text: str):
        """To create a new TODO"""
        await mt._create_todo(self.bot, ctx, name, text)

    @todo.command(name="editname")
    @commands.bot_has_permissions(embed_links=True)
    async def todo_editname(self, ctx: Context, name: str, *, new_name: str):
        """To edit the TODO name"""
        await mt._update_todo_name(self.bot, ctx, name, new_name)

    @todo.command(name="edittext")
    @commands.bot_has_permissions(embed_links=True)
    async def todo_edittext(self, ctx: Context, name: str, *, text: str):
        """To edit the TODO text"""
        await mt._update_todo_text(self.bot, ctx, name, text)

    @todo.command(name="delete")
    @commands.bot_has_permissions(embed_links=True)
    async def delete_todo(self, ctx: Context, *, name: str):
        """To delete the TODO task"""
        await mt._delete_todo(self.bot, ctx, name)

    @todo.command(name="settime", aliases=["set-time"])
    @commands.bot_has_permissions(embed_links=True)
    async def settime_todo(self, ctx: Context, name: str, *, deadline: ShortTime):
        """To set timer for your Timer"""
        await mt._set_timer_todo(self.bot, ctx, name, deadline.dt.timestamp())

    @commands.group(invoke_without_command=True)
    async def afk(self, ctx: Context, *, text: commands.clean_content = None):
        """To set AFK

        AFK will be removed once you message.
        If provided permissions, bot will add `[AFK]` as the prefix in nickname.
        The deafult AFK is on Server Basis
        """
        try:
            nick = f"[AFK] {ctx.author.display_name}"
            if len(nick) <= 32:  # discord limitation
                await ctx.author.edit(nick=nick, reason=f"{ctx.author} set their AFK")
        except discord.Forbidden:
            pass
        if not ctx.invoked_subcommand:
            if text and text.split(" ")[0].lower() in (
                "global",
                "till",
                "ignore",
                "after",
                "custom",
            ):
                return await ctx.send(
                    f"{ctx.author.mention} you can't set afk reason reserved words."
                )
            post = {
                "_id": ctx.message.id,
                "messageURL": ctx.message.jump_url,
                "messageAuthor": ctx.author.id,
                "guild": ctx.guild.id,
                "channel": ctx.channel.id,
                "at": ctx.message.created_at.timestamp(),
                "global": False,
                "text": text or "AFK",
                "ignoredChannel": [],
            }
            await ctx.send(f"{ctx.author.mention} AFK: {text or 'AFK'}")
            await self.bot.afk_collection.insert_one(post)
            self.bot.afk_users.add(ctx.author.id)

    @afk.command(name="global")
    async def _global(self, ctx: Context, *, text: commands.clean_content = None):
        """To set the AFK globally (works only if the bot can see you)"""
        post = {
            "_id": ctx.message.id,
            "messageURL": ctx.message.jump_url,
            "messageAuthor": ctx.author.id,
            "guild": ctx.guild.id,
            "channel": ctx.channel.id,
            "pings": [],
            "at": ctx.message.created_at.timestamp(),
            "global": True,
            "text": text or "AFK",
            "ignoredChannel": [],
        }
        await self.bot.afk_collection.insert_one(post)
        await ctx.send(f"{ctx.author.mention} AFK: {text or 'AFK'}")
        self.bot.afk_users.add(ctx.author.id)

    @afk.command(name="for")
    async def afk_till(
        self, ctx: Context, till: ShortTime, *, text: commands.clean_content = None
    ):
        """To set the AFK time"""
        if till.dt.timestamp() - ctx.message.created_at.timestamp() <= 120:
            return await ctx.send(f"{ctx.author.mention} time must be above 120s")
        post = {
            "_id": ctx.message.id,
            "messageURL": ctx.message.jump_url,
            "messageAuthor": ctx.author.id,
            "guild": ctx.guild.id,
            "channel": ctx.channel.id,
            "pings": [],
            "at": ctx.message.created_at.timestamp(),
            "global": True,
            "text": text or "AFK",
            "ignoredChannel": [],
        }
        await self.bot.afk_collection.insert_one(post)
        self.bot.afk_users.add(ctx.author.id)
        await ctx.send(
            f"{ctx.author.mention} AFK: {text or 'AFK'}\n> Your AFK status will be removed {discord.utils.format_dt(till.dt, 'R')}"
        )
        await self.create_timer(
            _event_name="remove_afk",
            expires_at=till.dt.timestamp(),
            created_at=ctx.message.created_at.timestamp(),
            extra={"name": "REMOVE_AFK", "main": {**post}},
            message=ctx.message,
        )

    @afk.command(name="after")
    async def afk_after(
        self, ctx: Context, after: ShortTime, *, text: commands.clean_content = None
    ):
        """To set the AFK future time"""
        if after.dt.timestamp() - ctx.message.created_at.timestamp() <= 120:
            return await ctx.send(f"{ctx.author.mention} time must be above 120s")
        post = {
            "_id": ctx.message.id,
            "messageURL": ctx.message.jump_url,
            "messageAuthor": ctx.author.id,
            "guild": ctx.guild.id,
            "channel": ctx.channel.id,
            "pings": [],
            "at": ctx.message.created_at.timestamp(),
            "global": True,
            "text": text or "AFK",
            "ignoredChannel": [],
        }
        await ctx.send(
            f"{ctx.author.mention} AFK: {text or 'AFK'}\n> Your AFK status will be set {discord.utils.format_dt(after.dt, 'R')}"
        )
        await self.create_timer(
            _event_name="set_afk",
            expires_at=after.dt.timestamp(),
            created_at=ctx.message.created_at.timestamp(),
            extra={"name": "SET_AFK", "main": {**post}},
            message=ctx.message,
        )

    @afk.command(name="custom")
    async def custom_afk(self, ctx: Context, *, flags: AfkFlags):
        """To set the custom AFK"""
        payload = {
            "_id": ctx.message.id,
            "text": flags.text or "AFK",
            "ignoredChannel": (
                [c.id for c in flags.ignore_channel] if flags.ignore_channel else []
            ),
            "global": flags._global,
            "at": ctx.message.created_at.timestamp(),
            "guild": ctx.guild.id,
            "messageAuthor": ctx.author.id,
            "messageURL": ctx.message.jump_url,
            "channel": ctx.channel.id,
            "pings": [],
        }

        if flags.after and flags._for:
            return await ctx.send(
                f"{ctx.author.mention} can not have both `after` and `for` argument"
            )

        if flags.after:
            await self.create_timer(
                _event_name="set_afk",
                expires_at=flags.after.dt.timestamp(),
                created_at=ctx.message.created_at.timestamp(),
                extra={"name": "SET_AFK", "main": {**payload}},
                message=ctx.message,
            )
            await ctx.send(
                f"{ctx.author.mention} AFK: {flags.text or 'AFK'}\n> Your AFK status will be set {discord.utils.format_dt(flags.after.dt, 'R')}"
            )
            return
        if flags._for:
            await self.create_timer(
                _event_name="remove_afk",
                expires_at=flags._for.dt.timestamp(),
                created_at=ctx.message.created_at.timestamp(),
                extra={"name": "REMOVE_AFK", "main": {**payload}},
                message=ctx.message,
            )
            await self.bot.afk_collection.insert_one(payload)
            self.bot.afk_users.add(ctx.author.id)
            await ctx.send(
                f"{ctx.author.mention} AFK: {flags.text or 'AFK'}\n> Your AFK status will be removed {discord.utils.format_dt(flags._for.dt, 'R')}"
            )
            return
        await self.bot.afk_collection.insert_one(payload)
        self.bot.afk_users.add(ctx.author.id)
        await ctx.send(f"{ctx.author.mention} AFK: {flags.text or 'AFK'}")

    async def cog_unload(self):
        self.server_stats_updater.cancel()

    @commands.command(aliases=["level"])
    @commands.bot_has_permissions(attach_files=True)
    async def rank(self, ctx: Context, *, member: discord.Member = None):
        """To get the level of the user"""
        member = member or ctx.author
        try:
            enable = self.bot.guild_configurations_cache[ctx.guild.id]["leveling"][
                "enable"
            ]
            if not enable:
                return await ctx.send(
                    f"{ctx.author.mention} leveling system is disabled in this server"
                )
        except KeyError:
            return await ctx.send(
                f"{ctx.author.mention} leveling system is disabled in this server"
            )
        else:
            collection: Collection = self.bot.guild_level_db[f"{member.guild.id}"]
            if data := await collection.find_one_and_update(
                {"_id": member.id},
                {"$inc": {"xp": 0}},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            ):
                level = int((data["xp"] // 42) ** 0.55)
                xp = await self.__get_required_xp(level + 1)
                rank = await self.__get_rank(collection=collection, member=member)
                file = await rank_card(
                    level,
                    rank,
                    member,
                    current_xp=data["xp"],
                    custom_background="#000000",
                    xp_color="#FFFFFF",
                    next_level_xp=xp,
                )
                await ctx.reply(file=file)
                return
            if ctx.author.id == member.id:
                return await ctx.reply(
                    f"{ctx.author.mention} you don't have any xp yet. Consider sending some messages"
                )
            return await ctx.reply(
                f"{ctx.author.mention} **{member}** don't have any xp yet."
            )

    @commands.command(aliases=["leaderboard"])
    @commands.bot_has_permissions(embed_links=True)
    async def lb(self, ctx: Context, *, limit: Optional[int] = None):
        """To display the Leaderboard"""
        limit = limit or 10
        collection = self.bot.guild_level_db[f"{ctx.guild.id}"]
        entries = await self.__get_entries(
            collection=collection, limit=limit, guild=ctx.guild
        )
        if not entries:
            return await ctx.send(
                f"{ctx.author.mention} there is no one in the leaderboard"
            )
        pages = SimplePages(entries, ctx=ctx, per_page=10)
        await pages.start()

    async def __get_required_xp(self, level: int) -> int:
        xp = 0
        while True:
            xp += 12
            lvl = int((xp // 42) ** 0.55)
            if lvl == level:
                return xp
            await asyncio.sleep(0)

    async def __get_rank(self, *, collection: Collection, member: discord.Member):
        countr = 0

        # you can't use `enumerate`
        async for data in collection.find({}, sort=[("xp", -1)]):
            countr += 1
            if data["_id"] == member.id:
                return countr

    async def __get_entries(
        self, *, collection: Collection, limit: int, guild: discord.Guild
    ):
        ls = []
        async for data in collection.find({}, limit=limit, sort=[("xp", -1)]):
            if member := await self.bot.get_or_fetch_member(guild, data["_id"]):
                ls.append(f"{member} (`{member.id}`)")
        return ls

    async def __fetch_suggestion_channel(
        self, guild: discord.Guild
    ) -> Optional[discord.TextChannel]:
        try:
            ch_id: Optional[int] = self.bot.guild_configurations_cache[guild.id][
                "suggestion_channel"
            ]
        except KeyError as e:
            raise commands.BadArgument("No suggestion channel is setup") from e
        else:
            if not ch_id:
                raise commands.BadArgument("No suggestion channel is setup")
            ch: Optional[discord.TextChannel] = self.bot.get_channel(ch_id)
            if ch is None:
                await self.bot.wait_until_ready()
                ch: discord.TextChannel = await self.bot.fetch_channel(ch_id)

            return ch

    async def get_or_fetch_message(
        self, msg_id: int, *, guild: discord.Guild, channel: discord.TextChannel = None
    ) -> Optional[discord.Message]:
        try:
            self.message[msg_id]
        except KeyError:
            if channel is None:
                try:
                    channel_id = self.bot.guild_configurations_cache[guild.id][
                        "suggestion_channel"
                    ]
                except KeyError as e:
                    raise commands.BadArgument("No suggestion channel is setup") from e
            msg = await self.__fetch_message_from_channel(
                message=msg_id, channel=self.bot.get_channel(channel_id)
            )
        else:
            msg = self.message[msg_id]["message"]

        return msg if msg.author.id == self.bot.user.id else None

    async def __fetch_message_from_channel(
        self, *, message: int, channel: discord.TextChannel
    ):
        async for msg in channel.history(
            limit=1,
            before=discord.Object(message + 1),
            after=discord.Object(message - 1),
        ):
            payload = {
                "message_author": msg.author,
                "message": msg,
                "message_downvote": self.__get_emoji_count_from__msg(
                    msg, emoji="\N{DOWNWARDS BLACK ARROW}"
                ),
                "message_upvote": self.__get_emoji_count_from__msg(
                    msg, emoji="\N{UPWARDS BLACK ARROW}"
                ),
            }
            self.message[message] = payload
            return msg

    def __get_emoji_count_from__msg(
        self,
        msg: discord.Message,
        *,
        emoji: Union[discord.Emoji, discord.PartialEmoji, str],
    ):
        for reaction in msg.reactions:
            if str(reaction.emoji) == str(emoji):
                return reaction.count

    async def __suggest(
        self,
        content: Optional[str] = None,
        *,
        embed: discord.Embed,
        ctx: Context,
        file: Optional[discord.File] = None,
    ) -> Optional[discord.Message]:
        channel: Optional[discord.TextChannel] = await self.__fetch_suggestion_channel(
            ctx.guild
        )
        if channel is None:
            raise commands.BadArgument(
                f"{ctx.author.mention} error fetching suggestion channel"
            )

        msg: discord.Message = await channel.send(content, embed=embed, file=file)

        await ctx.bulk_add_reactions(msg, *REACTION_EMOJI)
        thread = await msg.create_thread(name=f"Suggestion {ctx.author}")

        payload = {
            "message_author": msg.author,
            "message_downvote": 0,
            "message_upvote": 0,
            "message": msg,
            "thread": thread.id,
        }
        self.message[msg.id] = payload
        return msg

    async def __notify_on_suggestion(
        self, ctx: Context, *, message: discord.Message
    ) -> None:
        jump_url: str = message.jump_url
        _id: int = message.id
        content = (
            f"{ctx.author.mention} your suggestion being posted.\n"
            f"To delete the suggestion type: `{ctx.clean_prefix or await ctx.bot.get_guild_prefixes(ctx.guild.id)}suggest delete {_id}`\n"
            f"> {jump_url}"
        )
        try:
            await ctx.author.send(
                content,
                view=ctx.send_view(),
            )
        except discord.Forbidden:
            pass

    async def __notify_user(
        self,
        ctx: Context,
        user: Optional[discord.Member] = None,
        *,
        message: discord.Message,
        remark: str,
    ) -> None:
        if user is None:
            return

        remark = remark or "No remark was given"

        content = (
            f"{user.mention} your suggestion of ID: {message.id} had being updated.\n"
            f"By: {ctx.author} (`{ctx.author.id}`)\n"
            f"Remark: {remark}\n"
            f"> {message.jump_url}"
        )
        try:
            await user.send(
                content,
                view=ctx.send_view(),
            )
        except discord.Forbidden:
            pass

    @commands.group(aliases=["suggestion"], invoke_without_command=True)
    @commands.cooldown(1, 60, commands.BucketType.member)
    @commands.bot_has_permissions(embed_links=True, create_public_threads=True)
    async def suggest(self, ctx: Context, *, suggestion: commands.clean_content):
        """Suggest something. Abuse of the command may result in required mod actions"""

        if not ctx.invoked_subcommand:
            embed = discord.Embed(
                description=suggestion, timestamp=ctx.message.created_at, color=0xADD8E6
            )
            embed.set_author(
                name=str(ctx.author), icon_url=ctx.author.display_avatar.url
            )
            embed.set_footer(
                text=f"Author ID: {ctx.author.id}",
                icon_url=getattr(ctx.guild.icon, "url", ctx.author.display_avatar.url),
            )

            file: Optional[discord.File] = None

            if ctx.message.attachments and (
                ctx.message.attachments[0]
                .url.lower()
                .endswith(("png", "jpeg", "jpg", "gif", "webp"))
            ):
                _bytes = await ctx.message.attachments[0].read(use_cached=True)
                file = discord.File(io.BytesIO(_bytes), "image.jpg")
                embed.set_image(url="attachment://image.jpg")

            msg = await self.__suggest(ctx=ctx, embed=embed, file=file)
            await self.__notify_on_suggestion(ctx, message=msg)
            await ctx.message.delete(delay=0)

    @suggest.command(name="delete")
    @commands.cooldown(1, 60, commands.BucketType.member)
    @commands.bot_has_permissions(read_message_history=True)
    async def suggest_delete(self, ctx: Context, *, messageID: int):
        """To delete the suggestion you suggested"""

        msg: Optional[discord.Message] = await self.get_or_fetch_message(
            messageID, guild=ctx.guild
        )
        if not msg:
            return await ctx.send(
                f"{ctx.author.mention} Can not find message of ID `{messageID}`. Probably already deleted, or `{messageID}` is invalid"
            )

        if ctx.channel.permissions_for(ctx.author).manage_messages:
            await msg.delete(delay=0)
            await ctx.send(f"{ctx.author.mention} Done", delete_after=5)
            return

        if int(msg.embeds[0].footer.text.split(":")[1]) != ctx.author.id:
            return await ctx.send(
                f"{ctx.author.mention} You don't own that 'suggestion'"
            )

        await msg.delete(delay=0)
        await ctx.send(f"{ctx.author.mention} Done", delete_after=5)

    @suggest.command(name="stats", hidden=True)
    @commands.cooldown(1, 60, commands.BucketType.member)
    async def suggest_status(self, ctx: Context, *, messageID: int):
        """To get the statistics os the suggestion"""

        msg: Optional[discord.Message] = await self.get_or_fetch_message(
            messageID, guild=ctx.guild
        )
        if not msg:
            return await ctx.send(
                f"{ctx.author.mention} Can not find message of ID `{messageID}`. Probably already deleted, or `{messageID}` is invalid"
            )
        PAYLOAD: Dict[str, Any] = self.message[msg.id]

        table = TabularData()

        upvoter = [PAYLOAD["message_upvote"]]
        downvoter = [PAYLOAD["message_downvote"]]

        table.set_columns(["Upvote", "Downvote"])
        ls = list(zip_longest(upvoter, downvoter, fillvalue=""))
        table.add_rows(ls)

        embed = discord.Embed(title=f"Suggestion Statistics of message ID: {messageID}")
        embed.description = f"```\n{table.render()}```"

        if msg.content:
            embed.add_field(name="Flagged", value=msg.content)
        await ctx.send(content=msg.jump_url, embed=embed)

    @suggest.command(name="resolved")
    @commands.bot_has_guild_permissions(manage_threads=True)
    @commands.cooldown(1, 60, commands.BucketType.member)
    async def suggest_resolved(self, ctx: Context, *, thread_id: int):
        """To mark the suggestion as resolved"""
        msg: Optional[discord.Message] = await self.get_or_fetch_message(
            thread_id, guild=ctx.guild
        )

        if int(msg.embeds[0].footer.text.split(":")[1]) != ctx.author.id:
            return await ctx.send(
                f"{ctx.author.mention} You don't own that 'suggestion'"
            )

        thread: discord.Thread = await self.bot.getch(
            ctx.guild.get_channel, ctx.guild.fetch_channel, thread_id
        )
        if not msg or not thread:
            return await ctx.send(
                f"{ctx.author.mention} Can not find message of ID `{thread_id}`. Probably already deleted, or `{thread_id}` is invalid"
            )
        await thread.edit(
            archived=True,
            locked=True,
            reason=f"Suggestion resolved by {ctx.author} ({ctx.author.id})",
        )
        await ctx.send(f"{ctx.author.mention} Done", delete_after=5)

    @suggest.command(name="note", aliases=["remark"])
    @commands.check_any(commands.has_permissions(manage_messages=True), is_mod())
    async def add_note(self, ctx: Context, messageID: int, *, remark: str):
        """To add a note in suggestion embed"""
        msg: Optional[discord.Message] = await self.get_or_fetch_message(
            messageID, guild=ctx.guild
        )
        if not msg:
            return await ctx.send(
                f"{ctx.author.mention} Can not find message of ID `{messageID}`. Probably already deleted, or `{messageID}` is invalid"
            )

        embed: discord.Embed = msg.embeds[0]
        embed.clear_fields()
        embed.add_field(name="Remark", value=remark[:250])
        new_msg = await msg.edit(content=msg.content, embed=embed)
        self.message[new_msg.id]["message"] = new_msg

        user_id = int(embed.footer.text.split(":")[1])
        user = ctx.guild.get_member(user_id)
        await self.__notify_user(ctx, user, message=msg, remark=remark)

        await ctx.send(f"{ctx.author.mention} Done", delete_after=5)

    @suggest.command(name="clear", aliases=["cls"])
    @commands.check_any(commands.has_permissions(manage_messages=True), is_mod())
    async def clear_suggestion_embed(
        self,
        ctx: Context,
        messageID: int,
    ):
        """To remove all kind of notes and extra reaction from suggestion embed"""

        msg: Optional[discord.Message] = await self.get_or_fetch_message(
            messageID, guild=ctx.guild
        )
        if not msg:
            return await ctx.send(
                f"{ctx.author.mention} Can not find message of ID `{messageID}`. Probably already deleted, or `{messageID}` is invalid"
            )

        embed: discord.Embed = msg.embeds[0]
        embed.clear_fields()
        embed.color = 0xADD8E6
        new_msg = await msg.edit(embed=embed, content=None)
        self.message[new_msg.id]["message"] = new_msg

        for reaction in msg.reactions:
            if str(reaction.emoji) not in REACTION_EMOJI:
                await msg.clear_reaction(reaction.emoji)
        await ctx.send(f"{ctx.author.mention} Done", delete_after=5)

    @suggest.command(name="flag")
    @commands.check_any(commands.has_permissions(manage_messages=True), is_mod())
    async def suggest_flag(self, ctx: Context, messageID: int, flag: str):
        """To flag the suggestion.

        Avalibale Flags :-
        - INVALID
        - ABUSE
        - INCOMPLETE
        - DECLINE
        - APPROVED
        - DUPLICATE
        """

        msg: Optional[discord.Message] = await self.get_or_fetch_message(
            messageID, guild=ctx.guild
        )
        if not msg:
            return await ctx.send(
                f"{ctx.author.mention} Can not find message of ID `{messageID}`. Probably already deleted, or `{messageID}` is invalid"
            )

        if msg.author.id != self.bot.user.id:
            return await ctx.send(f"{ctx.author.mention} Invalid `{messageID}`")

        flag = flag.upper()
        try:
            payload: Dict[str, Union[int, str]] = OTHER_REACTION[flag]
        except KeyError:
            return await ctx.send(f"{ctx.author.mention} Invalid Flag")

        embed: discord.Embed = msg.embeds[0]
        embed.color = payload["color"]

        user_id = int(embed.footer.text.split(":")[1])
        user: Optional[discord.Member] = await self.bot.get_or_fetch_member(
            ctx.guild, user_id
        )
        await self.__notify_user(ctx, user, message=msg, remark="")

        content = f"Flagged: {flag} | {payload['emoji']}"
        new_msg = await msg.edit(content=content, embed=embed)
        self.message[new_msg.id]["message"] = new_msg

        await ctx.send(f"{ctx.author.mention} Done", delete_after=5)

    @Cog.listener(name="on_raw_message_delete")
    async def suggest_msg_delete(self, payload) -> None:
        if payload.message_id in self.message:
            del self.message[payload.message_id]

    @Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        await self.bot.wait_until_ready()
        if message.author.bot or message.guild is None:
            return

        ls = await self.bot.guild_configurations.find_one(
            {"_id": message.guild.id, "suggestion_channel": message.channel.id}
        )
        if not ls:
            return

        if message.channel.id != ls["suggestion_channel"]:
            return

        if _ := await self.__parse_mod_action(message):
            return

        context: Context = await self.bot.get_context(message, cls=Context)
        await self.suggest(context, suggestion=message.content)

    @Cog.listener()
    async def on_message_edit(
        self, before: discord.Message, after: discord.Message
    ) -> None:
        if after.id in self.message:
            self.message[after.id]["message"] = after

    @Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        await mt.add_reactor(self.bot, payload)

        if payload.message_id not in self.message:
            return

        if str(payload.emoji) not in REACTION_EMOJI:
            return

        if str(payload.emoji) == "\N{UPWARDS BLACK ARROW}":
            self.message[payload.message_id]["message_upvote"] += 1
        if str(payload.emoji) == "\N{DOWNWARDS BLACK ARROW}":
            self.message[payload.message_id]["message_downvote"] += 1

    @Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        await mt.remove_reactor(self.bot, payload)

        if payload.message_id not in self.message:
            return

        if str(payload.emoji) not in REACTION_EMOJI:
            return

        if str(payload.emoji) == "\N{UPWARDS BLACK ARROW}":
            self.message[payload.message_id]["message_upvote"] -= 1
        if str(payload.emoji) == "\N{DOWNWARDS BLACK ARROW}":
            self.message[payload.message_id]["message_downvote"] -= 1

    async def __parse_mod_action(self, message: discord.Message) -> Optional[bool]:
        if not self.__is_mod(message.author):
            return

        if message.content.upper() in OTHER_REACTION:
            context: Context = await self.bot.get_context(message, cls=Context)
            # cmd: commands.Command = self.bot.get_command("suggest flag")

            msg: Union[
                discord.Message, discord.DeletedReferencedMessage
            ] = message.reference.resolved

            if not isinstance(msg, discord.Message):
                return

            if msg.author.id != self.bot.user.id:
                return

            # await context.invoke(cmd, msg.id, message.content.upper())
            await self.suggest_flag(context, msg.id, message.content.upper())
            return True

    def __is_mod(self, member: discord.Member) -> bool:
        try:
            role_id = self.bot.guild_configurations_cache[member.guild.id]["mod_role"]
            if role_id is None:
                perms: discord.Permissions = member.guild_permissions
                if any([perms.manage_guild, perms.manage_messages]):
                    return True
            return member._roles.has(role_id)
        except KeyError:
            return False

    @commands.group(name="giveaway", aliases=["gw"], invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def giveaway(self, ctx: Context):
        """To create giveaway"""
        if not ctx.invoked_subcommand:
            post = await mt._make_giveaway(ctx)
            await self.create_timer(_event_name="giveaway", **post)

    @giveaway.command(name="drop")
    @commands.has_permissions(manage_guild=True)
    async def giveaway_drop(
        self,
        ctx: Context,
        duration: ShortTime,
        winners: Optional[int] = 1,
        *,
        prize: str = None,
    ):
        """To create giveaway in quick format"""
        if not prize:
            return await ctx.send(
                f"{ctx.author.mention} you didn't give the prize argument"
            )
        post = await mt._make_giveaway_drop(
            ctx, duration=duration, winners=winners, prize=prize
        )
        await self.create_timer(_event_name="giveaway", **post)

    @giveaway.command(name="end")
    @commands.has_permissions(manage_guild=True)
    async def giveaway_end(self, ctx: Context, messageID: int):
        """To end the giveaway"""
        if data := await self.bot.giveaways.find_one_and_update(
            {"message_id": messageID, "status": "ONGOING"}, {"$set": {"status": "END"}}
        ):
            await self.collection.delete_one({"_id": messageID})

            member_ids = await mt.end_giveaway(self.bot, **data)
            if not member_ids:
                return await ctx.send(f"{ctx.author.mention} no winners!")

            joiner = ">, <@".join([str(i) for i in member_ids])

            await ctx.send(
                f"Congrats <@{joiner}> you won {data.get('prize')}\n"
                f"> https://discord.com/channels/{data.get('guild_id')}/{data.get('giveaway_channel')}/{data.get('message_id')}"
            )

    @giveaway.command(name="reroll")
    @commands.has_permissions(manage_guild=True)
    async def giveaway_reroll(self, ctx: Context, messageID: int, winners: int = 1):
        """To end the giveaway"""
        if data := await self.bot.giveaways.find_one({"message_id": messageID}):
            if data["status"].upper() == "ONGOING":
                return await ctx.send(
                    f"{ctx.author.mention} can not reroll the ongoing giveaway"
                )

            data["winners"] = winners

            member_ids = await mt.end_giveaway(self.bot, **data)

            if not member_ids:
                return await ctx.send(f"{ctx.author.mention} no winners!")

            joiner = ">, <@".join([str(i) for i in member_ids])

            await ctx.send(
                f"Contragts <@{joiner}> you won {data.get('prize')}\n"
                f"> https://discord.com/channels/{data.get('guild_id')}/{data.get('giveaway_channel')}/{data.get('message_id')}"
            )
            return
        await ctx.send(
            f"{ctx.author.mention} no giveaway found on message ID: `{messageID}`"
        )

    @tasks.loop(seconds=600)
    async def server_stats_updater(self):
        for guild in self.bot.guilds:
            PAYLOAD = {
                "bots": len([m for m in guild.members if m.bot]),
                "members": len(guild.members),
                "channels": len(guild.channels),
                "roles": len(guild.roles),
                "emojis": len(guild.emojis),
                "text": guild.text_channels,
                "voice": guild.voice_channels,
                "categories": len(guild.categories),
            }
            try:
                stats_channels: Dict[str, Any] = self.bot.guild_configurations_cache[
                    guild.id
                ]["stats_channels"]
            except KeyError:
                pass
            else:
                for k, v in stats_channels.items():
                    if k != "role":
                        v: Dict[str, Any]
                        if channel := guild.get_channel(v["channel_id"]):
                            await channel.edit(
                                name=v["template"].format(PAYLOAD[k]),
                                reason="Updating server stats",
                            )

                if roles := stats_channels.get("role", []):
                    for role in roles:
                        r = guild.get_role(role["role_id"])
                        channel = guild.get_channel(role["channel_id"])
                        if channel and role:
                            await channel.edit(
                                name=role["template"].format(len(r.members)),
                                reason="Updating server stats",
                            )

    @server_stats_updater.before_loop
    async def before_server_stats_updater(self):
        await self.bot.wait_until_ready()
