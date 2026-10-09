import discord
from core import game
from .box import TIERS
from discord import app_commands
from discord.ext import commands
from core import emoji as rosieemoji

def pct(chance):
    return (
        f"{chance/100:.2f}"
        .rstrip("0")
        .rstrip(".")
        +"%"
    )

class OddsSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="pick a game",
            options=[
                discord.SelectOption(
                    label="Mystery Box",
                    value="box",
                    emoji="📦"
                ),
                discord.SelectOption(
                    label="Scratch-Off",
                    value="scratch",
                    emoji="🎟️"
                )
            ],
            row=0
        )

    async def callback(self,it:discord.Interaction):
        view=self.view

        if not await view.owned(it):
            return

        view.game=self.values[0]
        view.page=0
        view.sync()

        await it.response.edit_message(
            embed=view.embed(),
            view=view
        )

class OddsView(discord.ui.View):
    def __init__(self,user_id):
        super().__init__(
            timeout=180
        )

        self.user_id=user_id
        self.game="box"
        self.page=0
        self.add_item(
            OddsSelect()
        )
        self.sync()

    async def owned(self,it):
        if it.user.id==self.user_id:
            return True

        await it.response.send_message(
            "make ur own /odds",
            ephemeral=True
        )

        return False

    def embed(self):
        if self.game=="scratch":
            prizes=game.card()

            rewards="\n".join(
                f"`33.33%` • "
                f"{emoji} {name}"
                for emoji,kind,value,name
                in prizes
            )

            return discord.Embed(
                title="🎟️ scratch-off",
                description=(
                    f"**today's prizes**\n"
                    f"{rewards}\n\n"
                    "any prize ⊹ **74.55%**"
                ),
                color=discord.Color.dark_red()
            )

        tier=self.page+1
        cost,prizes=TIERS[tier]
        numerals=("i","ii","iii","iv","v")

        lines=[
            f"`{pct(chance):>6}` • {name}"
            for chance,kind,value,name
            in prizes
        ]

        embed=discord.Embed(
            title=(
                f"🎰 mystery box • "
                f"tier {numerals[self.page]}"
            ),
            description=(
                f'{rosieemoji.ROSE} **{cost:,} roses**\n\n'
                +"\n".join(lines)
            ),
            color=discord.Color.dark_red()
        )

        embed.set_footer(
            text=f"{self.page+1} / {len(TIERS)}"
        )

        return embed

    def sync(self):
        scratch=self.game=="scratch"
        self.first.disabled=scratch or self.page==0
        self.back.disabled=scratch or self.page==0
        self.next.disabled=scratch or self.page==len(TIERS)-1
        self.last.disabled=scratch or self.page==len(TIERS)-1

    @discord.ui.button(
        emoji="⏮️",
        style=discord.ButtonStyle.secondary,
        row=1
    )
    async def first(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        if not await self.owned(it):
            return

        self.page=0
        self.sync()

        await it.response.edit_message(
            embed=self.embed(),
            view=self
        )

    @discord.ui.button(
        emoji="◀️",
        style=discord.ButtonStyle.secondary,
        row=1
    )
    async def back(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        if not await self.owned(it):
            return

        self.page-=1
        self.sync()

        await it.response.edit_message(
            embed=self.embed(),
            view=self
        )

    @discord.ui.button(
        emoji="▶️",
        style=discord.ButtonStyle.secondary,
        row=1
    )
    async def next(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        if not await self.owned(it):
            return

        self.page+=1
        self.sync()

        await it.response.edit_message(
            embed=self.embed(),
            view=self
        )

    @discord.ui.button(
        emoji="⏭️",
        style=discord.ButtonStyle.secondary,
        row=1
    )
    async def last(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        if not await self.owned(it):
            return

        self.page=len(TIERS)-1
        self.sync()

        await it.response.edit_message(
            embed=self.embed(),
            view=self
        )

class Odds(commands.Cog):
    @app_commands.command(
        name="odds",
        description="view game odds"
    )
    async def odds(
        self,
        it:discord.Interaction
    ):
        view=OddsView(
            it.user.id
        )

        await it.response.send_message(
            embed=view.embed(),
            view=view
        )

async def setup(bot):
    await bot.add_cog(
        Odds()
    )
