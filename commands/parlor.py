from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from discord.http import Route

IMAGE=(
    Path(__file__).resolve().parents[1]
    /"assets"
    /"parlor"
    /"parlor.jpg"
)

class Parlor(commands.Cog):
    def __init__(self,bot):
        self.bot=bot
        self.managed=False

    async def registry(self):
        if self.managed:
            return

        app_id=(
            self.bot.application_id
            or self.bot.user.id
        )

        remote=await self.bot.http.request(
            Route(
                "GET",
                "/applications/{application_id}/commands",
                application_id=app_id
            )
        )

        for command in remote:
            if (
                int(command.get("type",0))==1
                and command.get("name")=="thorns"
            ):
                await self.bot.http.request(
                    Route(
                        "DELETE",
                        "/applications/{application_id}/commands/{command_id}",
                        application_id=app_id,
                        command_id=command["id"]
                    )
                )

        await self.bot.http.request(
            Route(
                "POST",
                "/applications/{application_id}/commands",
                application_id=app_id
            ),
            json={
                "name":"parlor",
                "description":"open rosie's parlor",
                "type":1
            }
        )

        self.managed=True

        print(
            "parlor command registry ✓"
        )

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            await self.registry()

        except Exception as error:
            print(
                f"parlor registry failed ⊹ {error}"
            )

    @app_commands.command(
        name="parlor",
        description="open rosie's parlor"
    )
    async def parlor(
        self,
        it:discord.Interaction
    ):
        if not IMAGE.exists():
            await it.response.send_message(
                "parlor wandered off 💔",
                ephemeral=True
            )
            return

        await it.response.send_message(
            file=discord.File(
                IMAGE,
                filename="parlor.jpg"
            )
        )

async def setup(bot):
    await bot.add_cog(
        Parlor(bot)
    )
