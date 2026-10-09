import sys
sys.dont_write_bytecode=True

import os

import discord
from core import database
from core import economy
from core import brewing
from core import petbuff
from core import privateconfig
from core import roots
from core import seasonal
from core import usage
from core import updates
from discord import app_commands
from discord.ext import commands
from core import guildconfig

TOKEN=os.environ["DISCORD_TOKEN"]

class UsageTree(app_commands.CommandTree):
    async def interaction_check(self,it:discord.Interaction):
        _payload=(
            it.data
            if isinstance(
                it.data,
                dict
            )
            else {}
        )

        _name=_payload.get(
            "name"
        )

        if (
            it.guild_id is not None
            and _name not in {
                "roses",
                "settings"
            }
        ):
            try:
                _channel=getattr(
                    it,
                    "channel",
                    None
                )

                _parent_id=getattr(
                    _channel,
                    "parent_id",
                    None
                )

                if not guildconfig.commandchannelallowed(
                    it.guild_id,
                    it.channel_id,
                    _parent_id
                ):
                    await it.response.send_message(
                        "nuh uh not here",
                        ephemeral=True
                    )

                    return False

            except Exception as error:
                print(
                    f"channel whitelist error ⊹ {error}"
                )

        try:
            payload=it.data if isinstance(it.data,dict) else {}
            name=payload.get("name")
            usage.hit(it.user.id,name)
            if name not in {"parlor","reaper","relic"}:
                seasonal.commandxp(it.user.id,name)
        except Exception as error:
            print(f"usage tracking error ⊹ {error}")

        try:
            updates.queue(
                it
            )
        except Exception as error:
            print(
                f"update queue error ⊹ {error}"
            )

        return True

class Rosie(commands.Bot):
    def __init__(self):
        intents=discord.Intents.default()

        super().__init__(
            command_prefix="!",
            intents=intents,
            status=discord.Status.dnd,
            tree_cls=UsageTree
        )

    async def setup_hook(self):
        for file in sorted(os.listdir("commands")):
            if (
                file.endswith(".py")
                and not file.startswith("_")
                and "." not in file[:-3]
            ):
                await self.load_extension(
                    f"commands.{file[:-3]}"
                )

        await self.load_extension(
            "core.reposts"
        )

        brewing.install()
        petbuff.install()
        roots.install()
        seasonal.install()

        loaded=self.tree.get_commands()

        print(
            f"loaded {len(loaded)}: "
            +", ".join(
                command.name
                for command in loaded
            )
        )

    async def on_message(self,message):
        if (
            message.guild is not None
            and not message.author.bot
        ):
            try:
                seasonal.messagexp(
                    message.author.id
                )
            except Exception as error:
                print(
                    f"season message XP ⊹ {error}"
                )

        await self.process_commands(
            message
        )

    async def on_ready(self):
        await self.change_presence(
            status=discord.Status.dnd
        )

        print(
            f"hiya {self.user} • dnd"
        )

privateconfig.apply()
economy.init()
economy.install()
database.init()
usage.init()
seasonal.init()
updates.init()

bot=Rosie()
bot.run(TOKEN)
