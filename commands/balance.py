import re
import sqlite3

import discord
from core import database
from core import game
from core import policy
from discord import app_commands
from discord.ext import commands
from core import emoji as rosieemoji




def uid(value):
    match=re.fullmatch(
        r"(?:<@!?)?(\d{15,22})>?",
        value.strip()
    )

    return int(match.group(1)) if match else None




def roserank(guild_id,user_id):
    if int(user_id) in policy.LEADERBOARD_HIDDEN:
        return 0

    guild_id=database.walletscope(
        guild_id
    )

    with sqlite3.connect(
        database.FILE
    ) as con:
        rows=con.execute(
            """SELECT user_id,roses
            FROM wallets
            WHERE guild_id=?
            AND roses>0""",
            (
                guild_id,
            )
        ).fetchall()

    scores=[
        (
            int(user),
            int(roses)
        )
        for user,roses in rows
        if int(user)
        not in policy.LEADERBOARD_HIDDEN
    ]

    scores.sort(
        key=lambda row:(
            -row[1],
            row[0]
        )
    )

    return next(
        (
            rank
            for rank,(user,roses)
            in enumerate(
                scores,
                1
            )
            if user==int(
                user_id
            )
        ),
        0
    )


def balanceembed(user_id,target,guild_id):
    roses,rings=database.wallet(
        guild_id,
        target.id
    )

    rank=roserank(
        guild_id,
        target.id
    )

    embed=discord.Embed(
        title=f"{rosieemoji.ROSE} balance",
        description=(
            f"**{roses:,} roses {rosieemoji.ROSE}**\n"
            f"**{rings:,} rings {rosieemoji.RING}**\n"
            f"-# rose rank ⊹ {rank}"
        ),
        color=discord.Color.dark_red()
    )

    embed.set_thumbnail(
        url=target.display_avatar.url
    )

    return embed






class Balance(commands.Cog):
    def __init__(self,bot):
        self.bot=bot

    @app_commands.command(
        name="balance",
        description="check a balance"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        user="user"
    )
    async def balance(
        self,
        it:discord.Interaction,
        user:str|None=None
    ):
        target=it.user
        deferred=False

        if user is not None:
            user_id=uid(
                user
            )

            if user_id is None:
                await it.response.send_message(
                    "gimme a user mention or id",
                    ephemeral=True
                )
                return

            target=it.guild.get_member(
                user_id
            )

            if target is None:
                await it.response.defer()
                deferred=True

                try:
                    target=await self.bot.fetch_user(
                        user_id
                    )

                except discord.NotFound:
                    await it.followup.send(
                        "cant find that user",
                        ephemeral=True
                    )
                    return

                except discord.HTTPException:
                    await it.followup.send(
                        "discord ate that lookup 💔 try again",
                        ephemeral=True
                    )
                    return

        game.touch(
            target.id
        )

        embed=balanceembed(
            it.user.id,
            target,
            it.guild_id
        )

        if deferred:
            await it.followup.send(
                embed=embed
            )

        else:
            await it.response.send_message(
                embed=embed
            )


async def setup(bot):
    await bot.add_cog(
        Balance(bot)
    )
