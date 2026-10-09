import secrets

import discord
from core import game
from core import brewing
from discord import app_commands
from discord.ext import commands
from core import emoji as rosieemoji

def energyline(data):
    maximum=int(
        data.get(
            "max_energy",
            brewing.MAX_ENERGY
        )
    )

    if data["energy"]>=maximum:
        regen="full"
    else:
        regen=(
            f"<t:{int(data['next'])}:R>"
        )

    return (
        f"energy ⊹ "
        f"**{data['energy']} / "
        f"{maximum}**\n"
        f"next ⊹ **{regen}**"
    )

def panel(user_id):
    data=brewing.forage_state(
        user_id
    )

    return discord.Embed(
        title="🌿 forage",
        description=(
            "go touch grass\n\n"
            f"{energyline(data)}\n\n"
            "pick somewhere to look"
        ),
        color=discord.Color.dark_red()
    )

def lootline(loot):
    lines=[]

    for key,amount in loot.items():
        cfg=brewing.INGREDIENTS[
            key
        ]

        name=(
            cfg["name"]
            if amount==1
            else cfg["plural"]
        )

        lines.append(
            f"{cfg['emoji']} ⊹ "
            f"**{amount} {name}**"
        )

    return "\n".join(
        lines
    )

class Location(discord.ui.Button):
    def __init__(
        self,
        key,
        disabled=False
    ):
        cfg=brewing.FORAGE[
            key
        ]

        super().__init__(
            emoji=cfg["emoji"],
            style=discord.ButtonStyle.secondary,
            disabled=disabled
        )

        self.key=key

    async def callback(
        self,
        it:discord.Interaction
    ):
        view=self.view

        if it.user.id!=view.user_id:
            await it.response.send_message(
                "make ur own /forage",
                ephemeral=True
            )
            return

        state=brewing.forage_state(
            it.user.id
        )

        if state["energy"]<1:
            await it.response.send_message(
                "out of energy ⊹ "
                f"<t:{int(state['next'])}:R>",
                ephemeral=True
            )
            return

        cfg=brewing.FORAGE[
            self.key
        ]

        await it.response.edit_message(
            embed=discord.Embed(
                title=(
                    f"{cfg['emoji']} "
                    f"{cfg['name']}"
                ),
                description=(
                    "pick one"
                ),
                color=discord.Color.dark_red()
            ),
            view=Search(
                it.user.id,
                self.key
            )
        )

class Places(discord.ui.View):
    def __init__(
        self,
        user_id
    ):
        super().__init__(
            timeout=3600
        )

        self.user_id=user_id

        state=brewing.forage_state(
            user_id
        )

        disabled=(
            state["energy"]<1
        )

        for key in brewing.FORAGE:
            self.add_item(
                Location(
                    key,
                    disabled
                )
            )

OBJECT_EMOJI={
    "thorny bush":"🥀",
    "fallen petals":rosieemoji.ROSE,
    "old trellis":"🪵",
    "cracked pot":"🪴",
    "something red":"❓",
    "fallen log":"🪵",
    "mushrooms":"🍄",
    "tangled brush":"🌿",
    "tree roots":"🌱",
    "old stump":"🪵",
    "hollow tree":"🕳️",
    "moonlit puddle":"💧",
    "moving grass":"🌿",
    "cold stone":"🪨",
    "something shiny":"✨"
}

class Object(discord.ui.Button):
    def __init__(
        self,
        location,
        label
    ):
        emoji=OBJECT_EMOJI.get(
            label
        )

        super().__init__(
            label=None if emoji else label,
            emoji=emoji,
            style=discord.ButtonStyle.secondary
        )

        self.location=location
        self.object=label

    async def callback(
        self,
        it:discord.Interaction
    ):
        view=self.view

        if it.user.id!=view.user_id:
            await it.response.send_message(
                "make ur own /forage",
                ephemeral=True
            )
            return

        result=brewing.forage(
            it.user.id,
            self.location
        )

        if not result["ok"]:
            await it.response.send_message(
                "out of energy ⊹ "
                f"<t:{int(result['next'])}:R>",
                ephemeral=True
            )
            return

        game.touch(
            it.user.id
        )

        cfg=brewing.FORAGE[
            self.location
        ]

        data={
            "energy":result["energy"],
            "next":result["next"],
            "max_energy":result.get(
                "max_energy",
                brewing.MAX_ENERGY
            ),
            "regen":result.get(
                "regen",
                brewing.ENERGY_REGEN
            )
        }

        await it.response.edit_message(
            embed=discord.Embed(
                title=(
                    f"{cfg['emoji']} "
                    f"{cfg['name']}"
                ),
                description=(
                    f"you searched the "
                    f"**{self.object}**.\n\n"
                    f"{lootline(result['loot'])}\n\n"
                    f"{energyline(data)}"
                ),
                color=discord.Color.dark_red()
            ),
            view=Again(
                it.user.id
            )
        )

class Search(discord.ui.View):
    def __init__(
        self,
        user_id,
        location
    ):
        super().__init__(
            timeout=180
        )

        self.user_id=user_id

        objects=secrets.SystemRandom().sample(
            list(
                brewing.FORAGE[
                    location
                ]["objects"]
            ),
            3
        )

        for label in objects:
            self.add_item(
                Object(
                    location,
                    label
                )
            )

class AgainButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            emoji="🔄",
            style=discord.ButtonStyle.success
        )

    async def callback(
        self,
        it:discord.Interaction
    ):
        view=self.view

        if it.user.id!=view.user_id:
            await it.response.send_message(
                "make ur own /forage",
                ephemeral=True
            )
            return

        await it.response.edit_message(
            embed=panel(
                it.user.id
            ),
            view=Places(
                it.user.id
            )
        )

class Again(discord.ui.View):
    def __init__(
        self,
        user_id
    ):
        super().__init__(
            timeout=180
        )

        self.user_id=user_id

        self.add_item(
            AgainButton()
        )

class Forage(commands.Cog):
    @app_commands.command(
        name="forage",
        description="go touch grass"
    )
    @app_commands.guild_only()
    async def forage(
        self,
        it:discord.Interaction
    ):
        game.touch(
            it.user.id
        )

        await it.response.send_message(
            embed=panel(
                it.user.id
            ),
            view=Places(
                it.user.id
            )
        )

async def setup(bot):
    brewing.init()
    await bot.add_cog(
        Forage()
    )
