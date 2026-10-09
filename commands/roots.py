import asyncio

import discord
from core import game
from core import roots
from discord import app_commands
from discord.ext import commands
from core import emoji as rosieemoji

LOCKS={}
ROMAN=("—","i","ii","iii","iv","v")
GROUPS=(
    (rosieemoji.ROSE,"pluck","pluck",(50,100,250,500)),
    ("🌱","garden","garden",(5,10,20,40)),
    ("🌿","forage","forage",(10,25,50,75)),
    ("🧪","brew","brew",(5,10,25)),
    ("🐾","pet","pet",(10,25,50)),
    ("⚔️","campaign","campaign",(5,)),
    ("🎁","boss","boss",(1,))
)

def panel(user_id,note=None):
    data=roots.state(user_id)
    lines=[
        f"buds ⊹ **{data['buds']}**",
        f"grown ⊹ **{data['grown']} / 20**",
        ""
    ]

    for key,info in roots.BRANCHES.items():
        level=data["levels"][key]
        lines.append(
            f"{info['emoji']} {info['name']} ⊹ **{ROMAN[level]}**"
        )

    if note:
        lines.extend(("",note))

    return discord.Embed(
        title="🌱 roots",
        description="\n".join(lines),
        color=discord.Color.dark_red()
    )

def branch_embed(user_id,branch,note=None):
    data=roots.state(user_id)
    info=roots.BRANCHES[branch]
    level=data["levels"][branch]

    if level:
        current=info["nodes"][level-1]
    else:
        current="ungrown"

    lines=[
        f"**{ROMAN[level]} / v**",
        "",
        f"current ⊹ {current}"
    ]

    if level<5:
        lines.extend((
            f"next ⊹ {info['nodes'][level]}",
            "",
            f'grow ⊹ **{roots.COSTS[level]:,} roses {rosieemoji.ROSE} + 1 bud 🌱**'
        ))
    else:
        lines.extend(("","fully grown ✦"))

    if note:
        lines.extend(("",note))

    return discord.Embed(
        title=f"{info['emoji']} {info['name']}",
        description="\n".join(lines),
        color=discord.Color.dark_red()
    )

def milestone_line(emoji,label,value,thresholds):
    done=sum(value>=target for target in thresholds)
    target=(
        thresholds[-1]
        if done>=len(thresholds)
        else thresholds[done]
    )
    shown=min(value,target)

    return (
        f"{emoji} {label} ⊹ "
        f"**{shown:,} / {target:,}** • "
        f"**{done} / {len(thresholds)}**"
    )

def milestones(user_id):
    data=roots.state(user_id)
    values=roots.metrics(user_id)
    lines=[
        milestone_line(
            emoji,
            label,
            values[key],
            thresholds
        )
        for emoji,label,key,thresholds in GROUPS
    ]

    lines.extend((
        "",
        (
            f"buds ⊹ **{data['earned']} earned • "
            f"{data['grown']} grown • {data['buds']} free**"
        )
    ))

    return discord.Embed(
        title="🌱 buds",
        description="\n".join(lines),
        color=discord.Color.dark_red()
    )

class BranchButton(discord.ui.Button):
    def __init__(self,branch):
        self.branch=branch
        super().__init__(
            emoji=roots.BRANCHES[branch]["emoji"],
            style=discord.ButtonStyle.secondary,
            row=0
        )

    async def callback(self,it:discord.Interaction):
        if it.user.id!=self.view.user_id:
            await it.response.send_message(
                "grow ur own roots",
                ephemeral=True
            )
            return

        await it.response.edit_message(
            embed=branch_embed(it.user.id,self.branch),
            view=BranchView(it.user.id,self.branch)
        )

class BudsButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            emoji="🌱",
            style=discord.ButtonStyle.success,
            row=0
        )

    async def callback(self,it:discord.Interaction):
        if it.user.id!=self.view.user_id:
            await it.response.send_message(
                "grow ur own roots",
                ephemeral=True
            )
            return

        await it.response.edit_message(
            embed=milestones(it.user.id),
            view=MilestonesView(it.user.id)
        )

class GrowButton(discord.ui.Button):
    def __init__(self,branch,disabled=False):
        self.branch=branch
        super().__init__(
            emoji="🌱",
            style=discord.ButtonStyle.success,
            disabled=disabled
        )

    async def callback(self,it:discord.Interaction):
        if it.user.id!=self.view.user_id:
            await it.response.send_message(
                "grow ur own roots",
                ephemeral=True
            )
            return

        lock=LOCKS.setdefault(
            it.user.id,
            asyncio.Lock()
        )

        async with lock:
            result=roots.grow(
                it.guild.id,
                it.user.id,
                self.branch
            )

        if not result["ok"]:
            if result["reason"]=="max":
                text="that branch is already fully grown"
            elif result["reason"]=="bud":
                text="you need another bud 🌱"
            elif result["reason"]=="roses":
                text=(
                    f"broke broski you need {result['need']:,} more {rosieemoji.ROSE}"
                )
            else:
                text="roots machine died"

            await it.response.send_message(
                text,
                ephemeral=True
            )
            return

        info=roots.BRANCHES[self.branch]
        note=(
            f"{info['emoji']} ⊹ "
            f"{info['name']} {ROMAN[result['level']]} grew"
        )

        await it.response.edit_message(
            embed=branch_embed(
                it.user.id,
                self.branch,
                note
            ),
            view=BranchView(
                it.user.id,
                self.branch
            )
        )

class BackButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            emoji="↩️",
            style=discord.ButtonStyle.secondary
        )

    async def callback(self,it:discord.Interaction):
        if it.user.id!=self.view.user_id:
            await it.response.send_message(
                "grow ur own roots",
                ephemeral=True
            )
            return

        await it.response.edit_message(
            embed=panel(it.user.id),
            view=RootsView(it.user.id)
        )

class RootsView(discord.ui.View):
    def __init__(self,user_id):
        super().__init__(timeout=300)
        self.user_id=user_id

        for branch in roots.BRANCHES:
            self.add_item(BranchButton(branch))

        self.add_item(BudsButton())

class BranchView(discord.ui.View):
    def __init__(self,user_id,branch):
        super().__init__(timeout=300)
        self.user_id=user_id
        self.branch=branch
        level=roots.level(user_id,branch)
        self.add_item(GrowButton(branch,level>=5))
        self.add_item(BackButton())

class MilestonesView(discord.ui.View):
    def __init__(self,user_id):
        super().__init__(timeout=300)
        self.user_id=user_id
        self.add_item(BackButton())

class Roots(commands.Cog):
    @app_commands.command(
        name="roots",
        description="grow permanent upgrades"
    )
    @app_commands.guild_only()
    async def roots(self,it:discord.Interaction):
        game.touch(it.user.id)

        await it.response.send_message(
            embed=_topflavor(panel(it.user.id), 'get ur hands dirty'),
            view=RootsView(it.user.id),
        )

async def setup(bot):
    roots.init()
    await bot.add_cog(Roots())

def _topflavor(
    embed,
    text
):
    if embed is None:
        return embed

    current=(
        embed.description
        or ""
    )

    if current.startswith(
        text
    ):
        return embed

    embed.description=(
        text
        if not current
        else (
            f"{text}\n\n"
            f"{current}"
        )
    )

    return embed

