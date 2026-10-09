import asyncio
import time

import discord
from core import game
from core import brewing
from discord import app_commands
from discord.ext import commands
from core import emoji as rosieemoji

LOCKS={}

def ingredient(
    key,
    amount
):
    cfg=brewing.INGREDIENTS[
        key
    ]

    name=(
        cfg["name"]
        if amount==1
        else cfg["plural"]
    )

    return (
        f"{amount} "
        f"{cfg['emoji']} {name}"
    )

def costline(key):
    return " + ".join(
        ingredient(
            name,
            amount
        )
        for name,amount
        in brewing.RECIPES[
            key
        ]["cost"].items()
    )

def panel(user_id):
    data=brewing.inventory(
        user_id
    )

    rose=(
        f"**{data['rose_charges']} charges**"
        if data["rose_charges"]
        else "**none**"
    )

    gxp=(
        f"**{data['gxp_charges']} plants**"
        if data["gxp_charges"]
        else "**none**"
    )

    return discord.Embed(
        title="🧪 rosie's brews",
        description=(
            f"what was in that?\n\n**satchel**\n{rosieemoji.ROSE} petals ⊹ **{data['petal']:,}**\n🌿 herbs ⊹ **{data['herb']:,}**\n💧 dew ⊹ **{data['dew']:,}**\n\n**active**\n{rosieemoji.ROSE} rose tonic ⊹ {rose}\n🌱 knowledge ⊹ {gxp}"
        ),
        color=discord.Color.dark_red()
    )

def recipes():
    lines=[]

    for key,cfg in brewing.RECIPES.items():
        lines.append(
            f"{cfg['emoji']} **{cfg['name']}**\n"
            f"{costline(key)}\n"
            f"{cfg['text']}"
        )

    return discord.Embed(
        title="🧪 recipes",
        description="\n\n".join(
            lines
        ),
        color=discord.Color.dark_red()
    )

def info():
    return discord.Embed(
        title="❓ ingredients",
        description=(
            rosieemoji.ROSE + ' petals ⊹ `/pluck`\n🌿 herbs ⊹ `/garden`\n💧 dew ⊹ `/pet` explore\n\nneed more? `/forage`'
        ),
        color=discord.Color.dark_red()
    )

def bottles(user_id):
    data=brewing.inventory(
        user_id
    )

    lines=[]

    for key,cfg in brewing.RECIPES.items():
        amount=data[
            "bottles"
        ][key]

        lines.append(
            f"{cfg['emoji']} • "
            f"**{amount:,}**"
        )

    if data["rose_charges"]:
        lines.append(
            f"\n{rosieemoji.ROSE} rose tonic active ⊹ **{data['rose_charges']} charges**"
        )

    if data["gxp_charges"]:
        lines.append(
            "🌱 knowledge active ⊹ "
            f"**{data['gxp_charges']} plants**"
        )

    return discord.Embed(
        title="🧴 bottles",
        description="\n".join(
            lines
        ),
        color=discord.Color.dark_red()
    )

def missingtext(missing):
    return " • ".join(
        ingredient(
            key,
            amount
        )
        for key,amount
        in missing.items()
    )

def brewed(key,result=None):
    cfg=brewing.RECIPES[
        key
    ]

    text=(
        "bottled ✦\n\n"
        f"{cfg['text']}\n"
        "saved to your bottles"
    )

    if result and result.get("roots_double"):
        text+="\n💧 ⊹ **bonus bottle**"

    return discord.Embed(
        title=(
            f"{cfg['emoji']} "
            f"{cfg['name']}"
        ),
        description=text,
        color=discord.Color.dark_red()
    )

def drank(key,text):
    cfg=brewing.RECIPES[
        key
    ]

    return discord.Embed(
        title=(
            f"{cfg['emoji']} "
            f"{cfg['name']}"
        ),
        description=text,
        color=discord.Color.dark_red()
    )

class Make(discord.ui.Button):
    def __init__(
        self,
        key
    ):
        cfg=brewing.RECIPES[
            key
        ]

        super().__init__(
            emoji=cfg["emoji"],
            style=discord.ButtonStyle.secondary
        )

        self.key=key

    async def callback(
        self,
        it:discord.Interaction
    ):
        view=self.view

        if it.user.id!=view.user_id:
            await it.response.send_message(
                "make ur own /brew",
                ephemeral=True
            )
            return

        lock=LOCKS.setdefault(
            it.user.id,
            asyncio.Lock()
        )

        async with lock:
            result=brewing.make(
                it.user.id,
                self.key
            )

        if not result["ok"]:
            await it.response.send_message(
                "missing ⊹ "
                f"**{missingtext(result['missing'])}**",
                ephemeral=True
            )
            return

        game.touch(
            it.user.id
        )

        await it.response.edit_message(
            embed=brewed(
                self.key,
                result
            ),
            view=RecipeView(
                it.user.id
            )
        )

class RecipeView(discord.ui.View):
    def __init__(
        self,
        user_id
    ):
        super().__init__(
            timeout=180
        )

        self.user_id=user_id

        for key in brewing.RECIPES:
            self.add_item(
                Make(key)
            )

class Drink(discord.ui.Button):
    def __init__(
        self,
        key,
        amount
    ):
        cfg=brewing.RECIPES[
            key
        ]

        super().__init__(
            label=f"• {amount}",
            emoji=cfg["emoji"],
            style=discord.ButtonStyle.secondary,
            disabled=amount<1
        )

        self.key=key

    async def callback(
        self,
        it:discord.Interaction
    ):
        view=self.view

        if it.user.id!=view.user_id:
            await it.response.send_message(
                "make ur own /brew",
                ephemeral=True
            )
            return

        lock=LOCKS.setdefault(
            it.user.id,
            asyncio.Lock()
        )

        async with lock:
            if self.key in (
                "rose_tonic",
                "knowledge"
            ):
                result=brewing.activate(
                    it.user.id,
                    self.key
                )

                if not result["ok"]:
                    if result["reason"]=="active":
                        await it.response.send_message(
                            "finish the one you drank first ⊹ "
                            f"**{result['charges']} left**",
                            ephemeral=True
                        )
                    else:
                        await it.response.send_message(
                            "you dont have one",
                            ephemeral=True
                        )
                    return

                text=(
                    "glug glug\n\n"
                    f"{brewing.RECIPES[self.key]['text']}\n"
                    f"**{result['charges']} charges ready**"
                )

            elif self.key=="overgrowth":
                if brewing.bottle(
                    it.user.id,
                    self.key
                )<1:
                    await it.response.send_message(
                        "you dont have one",
                        ephemeral=True
                    )
                    return

                import commands.garden as garden

                now=time.time()

                with garden.connect() as con:
                    con.execute(
                        "BEGIN IMMEDIATE"
                    )

                    rows=con.execute(
                        """SELECT plot,ready_at
                        FROM garden_v2_plants
                        WHERE user_id=?
                        AND ready_at>?""",
                        (
                            it.user.id,
                            now
                        )
                    ).fetchall()

                    if not rows:
                        await it.response.send_message(
                            "nothing is growing rn",
                            ephemeral=True
                        )
                        return

                    saved=0

                    for row in rows:
                        left=max(
                            0,
                            float(
                                row["ready_at"]
                            )-now
                        )

                        cut=left*.25
                        ready=(
                            float(
                                row["ready_at"]
                            )
                            -cut
                        )

                        saved+=cut

                        con.execute(
                            """UPDATE garden_v2_plants
                            SET ready_at=?
                            WHERE user_id=?
                            AND plot=?""",
                            (
                                ready,
                                it.user.id,
                                row["plot"]
                            )
                        )

                if not brewing.take(
                    it.user.id,
                    self.key
                ):
                    await it.response.send_message(
                        "bottle vanished somehow",
                        ephemeral=True
                    )
                    return

                text=(
                    f"the garden twitches.\n\n"
                    f"**{len(rows)} "
                    f"{'crop' if len(rows)==1 else 'crops'}** "
                    "grew 25% closer\n"
                    f"time pulled forward ⊹ "
                    f"**{round(saved/60):,}m total**"
                )

            else:
                if brewing.bottle(
                    it.user.id,
                    self.key
                )<1:
                    await it.response.send_message(
                        "you dont have one",
                        ephemeral=True
                    )
                    return

                import commands.pet as pet

                now=time.time()

                with pet.connect() as con:
                    con.execute(
                        "BEGIN IMMEDIATE"
                    )

                    found=pet.active(
                        con,
                        it.user.id,
                        now
                    )

                    if found is None:
                        await it.response.send_message(
                            "you need a pet first",
                            ephemeral=True
                        )
                        return

                    old=int(
                        found["energy"]
                    )

                    if old>=100:
                        await it.response.send_message(
                            "your pet is already full energy",
                            ephemeral=True
                        )
                        return

                    new=min(
                        100,
                        old+30
                    )

                    con.execute(
                        """UPDATE pets
                        SET energy=?
                        WHERE user_id=?
                        AND species=?""",
                        (
                            new,
                            it.user.id,
                            found["species"]
                        )
                    )

                if not brewing.take(
                    it.user.id,
                    self.key
                ):
                    await it.response.send_message(
                        "bottle vanished somehow",
                        ephemeral=True
                    )
                    return

                text=(
                    "somehow that worked.\n\n"
                    f"pet energy ⊹ "
                    f"**{old}% → {new}%**"
                )

        game.touch(
            it.user.id
        )

        await it.response.edit_message(
            embed=drank(
                self.key,
                text
            ),
            view=None
        )

class BottleView(discord.ui.View):
    def __init__(
        self,
        user_id
    ):
        super().__init__(
            timeout=180
        )

        self.user_id=user_id

        data=brewing.inventory(
            user_id
        )

        for key in brewing.RECIPES:
            self.add_item(
                Drink(
                    key,
                    data[
                        "bottles"
                    ][key]
                )
            )

class BrewMenu(discord.ui.Button):
    def __init__(self):
        super().__init__(
            emoji="🧪",
            style=discord.ButtonStyle.danger
        )

    async def callback(
        self,
        it:discord.Interaction
    ):
        view=self.view

        if it.user.id!=view.user_id:
            await it.response.send_message(
                "make ur own /brew",
                ephemeral=True
            )
            return

        await it.response.send_message(
            embed=recipes(),
            view=RecipeView(
                it.user.id
            ),
            ephemeral=True
        )

class Bottles(discord.ui.Button):
    def __init__(self):
        super().__init__(
            emoji="🧴",
            style=discord.ButtonStyle.secondary
        )

    async def callback(
        self,
        it:discord.Interaction
    ):
        view=self.view

        if it.user.id!=view.user_id:
            await it.response.send_message(
                "make ur own /brew",
                ephemeral=True
            )
            return

        await it.response.send_message(
            embed=bottles(
                it.user.id
            ),
            view=BottleView(
                it.user.id
            ),
            ephemeral=True
        )

class Recipes(discord.ui.Button):
    def __init__(self):
        super().__init__(
            emoji="❓",
            style=discord.ButtonStyle.secondary
        )

    async def callback(
        self,
        it:discord.Interaction
    ):
        view=self.view

        if it.user.id!=view.user_id:
            await it.response.send_message(
                "make ur own /brew",
                ephemeral=True
            )
            return

        await it.response.send_message(
            embed=info(),
            ephemeral=True
        )

class Main(discord.ui.View):
    def __init__(
        self,
        user_id
    ):
        super().__init__(
            timeout=3600
        )

        self.user_id=user_id

        self.add_item(
            BrewMenu()
        )
        self.add_item(
            Bottles()
        )
        self.add_item(
            Recipes()
        )

class Brew(commands.Cog):
    @app_commands.command(
        name="brew",
        description="brew something questionable"
    )
    @app_commands.guild_only()
    async def brew(
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
            view=Main(
                it.user.id
            )
        )

async def setup(bot):
    brewing.init()
    await bot.add_cog(
        Brew()
    )
