import discord
from core import database
from core import game
from discord import app_commands
from discord.ext import commands
from core import emoji as rosieemoji

class Daily(commands.Cog):
    def embed(self,result):
        reset=int(game.next_reset().timestamp())
        streak=result["streak"]
        word="day" if streak==1 else "days"
        bonus=""
        if result["bonus_roses"]:
            bonus=f"✦ **{streak} DAY STREAK**\n+{result['bonus_roses']:,} bonus roses {rosieemoji.ROSE}\n\n"
        elif result["bonus_rings"]:
            bonus=f"✦ **{streak} DAY STREAK**\n+{result['bonus_rings']:,} ring{'s' if result['bonus_rings']!=1 else ''} 💍\n\n"
        return discord.Embed(description=f'{bonus}{rosieemoji.ROSE} **daily**\n+500 roses {rosieemoji.ROSE}\n\n🔥 streak • **{streak} {word}**\nnext reset • <t:{reset}:R>\n\n🎟️ scratch unlocked',color=discord.Color.dark_red())

    @app_commands.command(name="daily",description="grab your daily roses")
    @app_commands.guild_only()
    async def daily(self,it:discord.Interaction):
        result=game.claim_daily(it.user.id)
        reset=int(game.next_reset().timestamp())
        streak=result["streak"]
        word="day" if streak==1 else "days"
        if not result["claimed"]:
            embed=discord.Embed(title=rosieemoji.ROSE + ' daily',description=f"already picked today's roses\n\n🔥 streak • **{streak} {word}**\nnext reset • <t:{reset}:R>\n\n🎟️ scratch unlocked",color=discord.Color.dark_red())
            await it.response.send_message(embed=embed,ephemeral=True)
            return
        database.walletadd(it.guild_id,it.user.id,roses=500+result["bonus_roses"])
        if result["bonus_rings"]:
            database.walletadd(it.guild_id,it.user.id,rings=result["bonus_rings"])
        await it.response.send_message(embed=self.embed(result))

async def setup(bot):
    await bot.add_cog(Daily())
