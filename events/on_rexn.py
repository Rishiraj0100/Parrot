from __future__ import annotations

from core import Parrot, Cog
from utilities.database import parrot_db, ticket_update
import discord
from datetime import datetime

collection = parrot_db['server_config']


class OnReaction(Cog, command_attrs=dict(hidden=True)):
    def __init__(self, bot: Parrot):
        self.bot = bot
        self.message_cache = {}
        self.msg_obj = {}

    @Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if data := collection.find_one({'_id': payload.guild_id}):
            if data['star_lock']:
                return
            try:
                starboard = data['starboard']
            except KeyError:
                return
            if starboard['emoji'] == str(reaction.emoji) and starboard['count'] == reaction.count:
                channel = self.bot.get_channel(starboard['channel'])
                if not channel:
                    return
                else:
                    embed = discord.Embed(
                        title=f"{reaction.message.author}", url=f"{reaction.message.jump_url}",
                        description=message.content, timestamp=datetime.utcnow(), color=reaction.message.author.color
                    ).set_footer(text=f"{reaction.message.guild.name}", icon_url=reaction.message.author.display_avatar.url)
                    msg = await channel.send(content=f'Star Count: {starboard['count']}', embed=embed)
                    self.message_cache[reaction.message.id] = {'emoji': starboard['emoji'], 'count': starboard['count']}
                    self.msg_obj[reaction.message.id] = msg
                    await msg.add_reaction(starboard['emoji'])
                    
    @Cog.listener()
    async def on_raw_reaction_add(self, payload):
        pass                

    @Cog.listener()
    async def on_reaction_remove(self, reaction, user):
        try:
            data = self.message_cache[reaction.message.id]
        except KeyError:
            return
        finally:
            if (reaction.message.emoji) == data['emoji'] and (data['count'] > reaction.count):
                try:
                    await self.msg_obj[reaction.message.id].delete()
                except Exception:
                    pass

    @Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        pass

    @Cog.listener()
    async def on_reaction_clear(self, message, reactions):
        pass

    @Cog.listener()
    async def on_raw_reaction_clear(self, payload):
        pass

    @Cog.listener()
    async def on_reaction_clear_emoji(self, reaction):
        pass

    @Cog.listener()
    async def on_raw_reaction_clear_emoji(self, payload):
        pass


def setup(bot):
    bot.add_cog(OnReaction(bot))
