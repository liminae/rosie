import secrets

import discord
from core import casino as casino
from core import game
from core import petbuff
from discord import app_commands
from discord.ext import commands
from core import emoji as rosieemoji

OUTCOMES=(
    (5900,0,"🥀 | 🌙 | 🍒"),
    (1200,100,rosieemoji.ROSE + ' | 🌙 | ' + rosieemoji.ROSE),
    (1400,200,"🍒 | 🍒 | 🥀"),
    (800,200,"🌙 | 🌙 | 🌙"),
    (400,300,"🍒 | 🍒 | 🍒"),
    (200,500,"💎 | 💎 | 💎"),
    (100,1000,rosieemoji.ROSE + ' | ' + rosieemoji.ROSE + ' | ' + rosieemoji.ROSE)
)

def roll():
    n=secrets.randbelow(10000)

    for chance,mult,combo in OUTCOMES:
        if n<chance:
            return mult,combo
        n-=chance

    raise RuntimeError(
        "slots odds died"
    )

class Slots(commands.Cog):
    @app_commands.command(
        name="slots",
        description="spin the slots"
    )
    @app_commands.guild_only()
    async def slots(
        self,
        it:discord.Interaction,
        bet:int
    ):
        game.touch(it.user.id)

        mult,combo=roll()
        base=bet*mult//100
        profit=max(0,base-bet)

        bonus=(
            petbuff.bonus(
                it.user.id,
                "casino",
                profit
            )
            if profit
            else 0
        )

        result=casino.play(
            it.guild.id,
            it.user.id,
            bet,
            50,
            500,
            base+bonus
        )

        if not result["ok"]:
            await it.response.send_message(
                casino.error(result),
                ephemeral=True
            )
            return

        if mult==0:
            outcome="nothing"
        elif mult==100:
            outcome="push"
        elif mult==1000:
            outcome=(
                f'**JACKPOT**\n+{profit:,} roses {rosieemoji.ROSE}'
            )
        else:
            outcome=(
                f'+{profit:,} roses {rosieemoji.ROSE}'
            )

        if bonus:
            outcome+=(
                f'\n🐈\u200d⬛ lucky paw ⊹ **+{bonus:,} roses {rosieemoji.ROSE}**'
            )

        await it.response.send_message(
            embed=discord.Embed(
                title="🎰 slots",
                description=(
                    f'**{combo}**\n\nbet ⊹ **{bet:,} roses {rosieemoji.ROSE}**\n{outcome}'
                ),
                color=discord.Color.dark_red()
            )
        )

async def setup(bot):
    await bot.add_cog(Slots())
