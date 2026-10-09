import sqlite3
import time

import discord
from core import database
from core import game
from core import policy
from discord import app_commands
from discord.ext import commands
from . import garden
from core import emoji as rosieemoji

def scythes(user):
    try:
        with sqlite3.connect(game.DB) as con:
            row=con.execute(
                "SELECT scythes FROM reaper_users WHERE user_id=?",
                (user,)
            ).fetchone()
        return row[0] if row else 0
    except sqlite3.OperationalError:
        return 0

def bossmvps(user):
    try:
        with sqlite3.connect(database.FILE) as con:
            row=con.execute(
                "SELECT mvps FROM boss_users WHERE user_id=?",
                (user,)
            ).fetchone()
        return row[0] if row else 0
    except sqlite3.OperationalError:
        return 0

def walletusers(guild_id):
    try:
        with sqlite3.connect(database.FILE) as con:
            rows=con.execute(
                "SELECT user_id FROM wallets WHERE guild_id=?",
                (
                    guild_id,
                )
            ).fetchall()

        return {
            int(row[0])
            for row in rows
        }

    except sqlite3.OperationalError:
        return set()

def bossusers():
    try:
        with sqlite3.connect(database.FILE) as con:
            rows=con.execute(
                "SELECT user_id FROM boss_users"
            ).fetchall()
        return {int(row[0]) for row in rows}
    except sqlite3.OperationalError:
        return set()

def sins(user):
    try:
        with sqlite3.connect(game.DB) as con:
            row=con.execute(
                "SELECT sins FROM sin_users WHERE user_id=?",
                (user,)
            ).fetchone()
        return row[0] if row else 0
    except sqlite3.OperationalError:
        return 0

def pairs():
    now=time.time()

    try:
        with sqlite3.connect(database.FILE) as con:
            rows=con.execute(
                "SELECT user1_id,user2_id,married_at,ended_at FROM marriages"
            ).fetchall()
    except sqlite3.OperationalError:
        return []

    out=[]

    for proposer,partner,started,ended in rows:
        if proposer in policy.LEADERBOARD_HIDDEN or partner in policy.LEADERBOARD_HIDDEN:
            continue

        age=max(0,(ended or now)-started)
        out.append((proposer,partner,age,started))

    out.sort(key=lambda x:(-x[2],x[0],x[1]))
    return out

def duration(seconds):
    days=int(seconds//86400)
    return f"{days:,} day" if days==1 else f"{days:,} days"

def gardenxp(user):
    with garden.connect() as con:
        row=con.execute(
            "SELECT xp FROM garden_v2_users WHERE user_id=?",
            (user,)
        ).fetchone()

    return int(row["xp"]) if row else 0


def gardenusers():
    with garden.connect() as con:
        return {
            int(row["user_id"])
            for row in con.execute(
                """SELECT user_id
                FROM garden_v2_users
                WHERE xp>0"""
            )
        }


def gardenfmt(xp):
    level=garden.lvl(xp)
    unlocked=sum(
        1
        for plant in garden.PLANTS.values()
        if level>=plant["level"]
    )
    return f"lvl {level:,}"


OPTIONS={
    "roses":(
        rosieemoji.ROSE + ' roses',
        lambda user,stats,guild_id:database.wallet(guild_id,user)[0],
        lambda n:f"{n:,}"
    ),
    "rings":(
        "💍 rings",
        lambda user,stats,guild_id:database.wallet(guild_id,user)[1],
        lambda n:f"{n:,}"
    ),
    "garden_level":(
        "🌱 garden level",
        lambda user,stats,guild_id:gardenxp(user),
        gardenfmt
    ),
    "daily_streak":(
        "🔥 current streak",
        lambda user,stats,guild_id:stats[user]["daily_streak"],
        lambda n:f"{n:,} days"
    ),
    "daily_best":(
        "🏆 best streak",
        lambda user,stats,guild_id:stats[user]["daily_best"],
        lambda n:f"{n:,} days"
    ),
    "boxes_opened":(
        "📦 boxes opened",
        lambda user,stats,guild_id:stats[user]["boxes_opened"],
        lambda n:f"{n:,}"
    ),
    "scratch_jackpots":(
        "🎟️ scratch jackpots",
        lambda user,stats,guild_id:stats[user]["scratch_jackpots"],
        lambda n:f"{n:,}"
    ),
    "scythes":(
        "💀 scythes",
        lambda user,stats,guild_id:scythes(user),
        lambda n:f"{n:,}"
    ),
    "sins":(
        "♦️ sins",
        lambda user,stats,guild_id:sins(user),
        lambda n:f"{n:,}"
    ),
    "boss_mvps":(
        "🎁 boss mvps",
        lambda user,stats,guild_id:bossmvps(user),
        lambda n:f"{n:,}"
    ),
    "robux_redeemed":(
        "💸 robux redeemed",
        lambda user,stats,guild_id:stats[user]["robux_redeemed"],
        lambda n:f"{n:,}"
    )
}

SELECTS=[
    ("roses","roses",rosieemoji.ROSE),
    ("rings","rings","💍"),
    ("daily_streak","current streak","🔥"),
    ("daily_best","best streak","🏆"),
    ("marriage","longest marriage","💞"),
    ("boxes_opened","boxes opened","📦"),
    ("garden_level","garden level","🌱"),
    ("scratch_jackpots","scratch jackpots","🎟️"),
    ("scythes","scythes","💀"),
    ("sins","sins","♦️"),
    ("boss_mvps","boss mvps","🎁"),
    ("robux_redeemed","robux redeemed","💸")
]

class LeaderboardSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="pick a leaderboard",
            options=[
                discord.SelectOption(
                    label=label,
                    value=value,
                    emoji=emoji
                )
                for value,label,emoji in SELECTS
            ],
            row=0
        )

    async def callback(self,it:discord.Interaction):
        if it.user.id!=self.view.user_id:
            await it.response.send_message(
                "make ur own /leaderboard",
                ephemeral=True
            )
            return

        self.view.metric=self.values[0]
        self.view.page=0

        await it.response.edit_message(
            embed=self.view.embed(),
            view=self.view
        )

class LeaderboardView(discord.ui.View):
    PER_PAGE=10

    def __init__(self,user_id,guild_id):
        super().__init__(timeout=180)
        self.user_id=user_id
        self.guild_id=guild_id
        self.metric="roses"
        self.page=0
        self.add_item(LeaderboardSelect())

    def page_data(self,rows):
        pages=max(
            1,
            (len(rows)+self.PER_PAGE-1)//self.PER_PAGE
        )

        self.page=max(
            0,
            min(self.page,pages-1)
        )

        self.first.disabled=self.page==0
        self.previous.disabled=self.page==0
        self.next.disabled=self.page>=pages-1
        self.last.disabled=self.page>=pages-1

        start=self.page*self.PER_PAGE

        return (
            rows[start:start+self.PER_PAGE],
            start,
            pages
        )

    def marriage(self):
        rows=pairs()
        shown,start,pages=self.page_data(rows)

        lines=[
            f"**{i}.** <@{a}> ♡ <@{b}> • "
            f"{duration(age)} • <t:{int(married)}:f>"
            for i,(a,b,age,married)
            in enumerate(shown,start+1)
        ]

        if not lines:
            lines=["nobody yet"]

        rank=None
        mine=0

        for i,(a,b,age,married) in enumerate(rows,1):
            if self.user_id in (a,b):
                rank=i
                mine=age
                break

        if self.user_id in policy.LEADERBOARD_HIDDEN:
            bottom="0"
        else:
            bottom=(
                f"#{rank} • {duration(mine)}"
                if rank
                else "unranked"
            )

        embed=discord.Embed(
            title="🏆 leaderboard",
            description=(
                "**💞 longest marriage**\n\n"
                +"\n".join(lines)
                +f"\n\n**your pair** ⊹ {bottom}"
            ),
            color=discord.Color.dark_red()
        )

        embed.set_footer(
            text=f"{self.page+1} / {pages}"
        )

        return embed

    def embed(self):
        if self.metric=="marriage":
            return self.marriage()

        stats=game.all_stats()

        if self.user_id not in stats:
            game.touch(self.user_id)
            stats=game.all_stats()

        label,getter,fmt=OPTIONS[self.metric]

        scores=[]
        mine=0
        hidden=self.user_id in policy.LEADERBOARD_HIDDEN

        users=set(stats)

        if self.metric in {"roses","rings"}:
            users.update(
                walletusers(
                    self.guild_id
                )
            )

        elif self.metric=="garden_level":
            users.update(
                gardenusers()
            )

        elif self.metric=="boss_mvps":
            users.update(
                bossusers()
            )

        for user in users:
            if user in policy.LEADERBOARD_HIDDEN:
                continue

            try:
                score=getter(user,stats,self.guild_id)
            except Exception:
                score=0

            if user==self.user_id:
                mine=score

            if score>0:
                scores.append((user,score))

        scores.sort(
            key=lambda x:(-x[1],x[0])
        )

        shown,start,pages=self.page_data(scores)

        lines=[
            f"**{i}.** <@{user}> • {fmt(score)}"
            for i,(user,score)
            in enumerate(shown,start+1)
        ]

        if not lines:
            lines=["nobody yet"]

        rank=next(
            (
                i
                for i,(user,score)
                in enumerate(scores,1)
                if user==self.user_id
            ),
            None
        )

        if hidden:
            bottom="0"
        else:
            bottom=(
                f"#{rank} • {fmt(mine)}"
                if rank
                else f"unranked • {fmt(mine)}"
            )

        embed=discord.Embed(
            title="🏆 leaderboard",
            description=(
                f"**{label}**\n\n"
                +"\n".join(lines)
                +f"\n\n**your rank** ⊹ {bottom}"
            ),
            color=discord.Color.dark_red()
        )

        embed.set_footer(
            text=f"{self.page+1} / {pages}"
        )

        return embed

    @discord.ui.button(
        emoji="⏪",
        style=discord.ButtonStyle.secondary,
        row=1
    )
    async def first(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        if it.user.id!=self.user_id:
            await it.response.send_message(
                "make ur own /leaderboard",
                ephemeral=True
            )
            return

        self.page=0

        await it.response.edit_message(
            embed=self.embed(),
            view=self
        )

    @discord.ui.button(
        emoji="◀️",
        style=discord.ButtonStyle.secondary,
        row=1
    )
    async def previous(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        if it.user.id!=self.user_id:
            await it.response.send_message(
                "make ur own /leaderboard",
                ephemeral=True
            )
            return

        self.page=max(0,self.page-1)

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
        if it.user.id!=self.user_id:
            await it.response.send_message(
                "make ur own /leaderboard",
                ephemeral=True
            )
            return

        self.page+=1

        await it.response.edit_message(
            embed=self.embed(),
            view=self
        )

    @discord.ui.button(
        emoji="⏩",
        style=discord.ButtonStyle.secondary,
        row=1
    )
    async def last(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        if it.user.id!=self.user_id:
            await it.response.send_message(
                "make ur own /leaderboard",
                ephemeral=True
            )
            return

        self.page=10**9

        await it.response.edit_message(
            embed=self.embed(),
            view=self
        )

class Leaderboard(commands.Cog):
    @app_commands.command(
        name="leaderboard",
        description="see who's winning"
    )
    @app_commands.guild_only()
    async def leaderboard(self,it:discord.Interaction):
        await it.response.defer()
        game.touch(it.user.id)
        view=LeaderboardView(it.user.id,it.guild.id)
        await it.followup.send(
            embed=view.embed(),
            view=view
        )

async def setup(bot):
    await bot.add_cog(Leaderboard())
