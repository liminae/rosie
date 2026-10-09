import secrets

import discord
from core import casino as casino
from core import game
from core import petbuff
from discord import app_commands
from discord.ext import commands
from core import emoji as rosieemoji

WIN=4200

class Coinflip(commands.Cog):
    @app_commands.command(
        name="cf",
        description="flip a coin"
    )
    @app_commands.guild_only()
    @app_commands.choices(side=[
        app_commands.Choice(
            name="heads",
            value="heads"
        ),
        app_commands.Choice(
            name="tails",
            value="tails"
        )
    ])
    async def cf(
        self,
        it:discord.Interaction,
        bet:int,
        side:app_commands.Choice[str]
    ):
        game.touch(it.user.id)

        win=secrets.randbelow(10000)<WIN
        coin=(
            side.value
            if win
            else (
                "tails"
                if side.value=="heads"
                else "heads"
            )
        )

        bonus=(
            petbuff.bonus(
                it.user.id,
                "casino",
                bet
            )
            if win
            else 0
        )

        payout=(
            bet*2+bonus
            if win
            else 0
        )

        result=casino.play(
            it.guild.id,
            it.user.id,
            bet,
            100,
            1000,
            payout
        )

        if not result["ok"]:
            await it.response.send_message(
                casino.error(result),
                ephemeral=True
            )
            return

        text=(
            f'bet ⊹ **{bet:,} roses {rosieemoji.ROSE}**\nyou ⊹ **{side.value}**\n\ncoin ⊹ **{coin}**'
        )

        if win:
            text+=(
                f'\nwon ⊹ **+{bet:,} roses {rosieemoji.ROSE}**'
            )

            if bonus:
                text+=(
                    f'\n🐈\u200d⬛ lucky paw ⊹ **+{bonus:,} roses {rosieemoji.ROSE}**'
                )
        else:
            text+="\nmissed"

        await it.response.send_message(
            embed=discord.Embed(
                title="🪙 coinflip",
                description=text,
                color=discord.Color.dark_red()
            )
        )

async def setup(bot):
    await bot.add_cog(Coinflip())
