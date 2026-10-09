import importlib
import sqlite3
import time
from datetime import datetime

import discord
from core import database
from core import game as core
from discord.ext import commands,tasks

def connect():
    con=sqlite3.connect(
        core.DB,
        timeout=10
    )
    con.row_factory=sqlite3.Row
    return con

def rconnect():
    con=sqlite3.connect(
        database.FILE,
        timeout=10
    )
    con.row_factory=sqlite3.Row
    return con

def init():
    with connect() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS event_reposts(
                kind TEXT NOT NULL,
                game_id INTEGER NOT NULL,
                day TEXT NOT NULL,
                message_id INTEGER,
                created_at REAL NOT NULL,
                PRIMARY KEY(kind,game_id,day)
            )"""
        )

def startday(state):
    value=state.get(
        "started_at"
    )

    if value is None:
        return None

    return datetime.fromtimestamp(
        float(value),
        core.ET
    ).date().isoformat()

def posted(kind,game_id,day):
    with connect() as con:
        row=con.execute(
            """SELECT 1
            FROM event_reposts
            WHERE kind=?
            AND game_id=?
            AND day=?""",
            (
                kind,
                game_id,
                day
            )
        ).fetchone()

    return row is not None

def mark(kind,game_id,day,message_id):
    with connect() as con:
        con.execute(
            """INSERT OR IGNORE INTO event_reposts(
                kind,
                game_id,
                day,
                message_id,
                created_at
            ) VALUES(?,?,?,?,?)""",
            (
                kind,
                game_id,
                day,
                message_id,
                time.time()
            )
        )

def messageday(message_id):
    if not message_id:
        return None

    try:
        made=discord.utils.snowflake_time(
            int(message_id)
        )

        return made.astimezone(
            core.ET
        ).date().isoformat()

    except (
        TypeError,
        ValueError,
        OverflowError
    ):
        return None

def sinstats(game_id):
    with connect() as con:
        row=con.execute(
            """SELECT
            COUNT(*) AS picks,
            COUNT(DISTINCT user_id) AS participants
            FROM sin_choices
            WHERE game_id=?""",
            (game_id,)
        ).fetchone()

    return (
        int(row["participants"]),
        int(row["picks"])
    )

def sinembed(mod,state):
    participants,picks=sinstats(
        state["id"]
    )

    ranks=mod.standings(
        state["id"]
    )

    if ranks:
        board="\n".join(
            f"**{i}.** <@{row['user_id']}> "
            f"⊹ {row['score']:.3f}"
            for i,row in enumerate(
                ranks[:5],
                1
            )
        )

    else:
        board="nobody yet"

    text=(
        f"participants ⊹ **{participants:,}**\n"
        f"season picks ⊹ **{picks:,}**\n\n"
        f"**overall**\n"
        f"{board}\n\n"
        f"pick **1 - {state['max_number']}**\n"
        f"closes ⊹ "
        f"<t:{mod.midnight_after(state['current_day'])}:R>"
    )

    return discord.Embed(
        title=f"♦️ sin - day {state['day_no']}",
        description=text,
        color=discord.Color.dark_red()
    )

def relicparticipants(game_id):
    try:
        with rconnect() as con:
            row=con.execute(
                """SELECT COUNT(*) AS participants
                FROM relic_players
                WHERE game_id=?""",
                (game_id,)
            ).fetchone()

        return int(
            row["participants"]
        )

    except sqlite3.Error:
        return 0

def relicembed(mod,state):
    embed=mod.embed(
        state
    )

    participants=relicparticipants(
        state["id"]
    )

    embed.description=(
        f"participants ⊹ **{participants:,}**\n\n"
        f"{embed.description or ''}"
    ).strip()

    return embed

async def getchannel(bot,channel_id):
    found=bot.get_channel(
        channel_id
    )

    if found is not None:
        return found

    try:
        return await bot.fetch_channel(
            channel_id
        )

    except discord.HTTPException:
        return None

async def disable_old_relic(
    bot,
    mod,
    state,
    new_message_id
):
    old=state.get(
        "message_id"
    )

    if (
        not old
        or int(old)==int(new_message_id)
    ):
        return

    channel=await getchannel(
        bot,
        state["channel_id"]
    )

    if channel is None:
        return

    try:
        message=await channel.fetch_message(
            int(old)
        )

        await message.edit(
            view=mod.RelicView(
                bot,
                True
            )
        )

    except discord.HTTPException:
        pass

class EventReposts(commands.Cog):
    def __init__(self,bot):
        self.bot=bot
        self.loop.start()

    def cog_unload(self):
        self.loop.cancel()

    async def sins(self,today):
        mod=importlib.import_module(
            "commands.sin"
        )

        for state in mod.active_real_games():
            try:
                game_id=state["id"]

                if startday(state)==today:
                    continue

                if posted(
                    "sin",
                    game_id,
                    today
                ):
                    continue

                if state.get(
                    "current_day"
                )!=today:
                    continue

                channel=await getchannel(
                    self.bot,
                    state["channel_id"]
                )

                if channel is None:
                    continue

                message=await channel.send(
                    embed=sinembed(
                        mod,
                        state
                    ),
                    view=mod.SinView(
                        self.bot
                    )
                )

                mark(
                    "sin",
                    game_id,
                    today,
                    message.id
                )

            except Exception as error:
                print(
                    f"sin daily repost "
                    f"game {state.get('id','?')}: "
                    f"{type(error).__name__}: "
                    f"{error}"
                )

    async def relics(self,today):
        mod=importlib.import_module(
            "commands.relic"
        )

        for state in mod.games():
            message=None

            try:
                game_id=state["id"]

                if startday(state)==today:
                    continue

                if state["ends_at"]<=time.time():
                    continue

                if posted(
                    "relic",
                    game_id,
                    today
                ):
                    continue

                current=state.get(
                    "message_id"
                )

                if (
                    current
                    and messageday(
                        current
                    )==today
                ):
                    mark(
                        "relic",
                        game_id,
                        today,
                        current
                    )

                    continue

                channel=await getchannel(
                    self.bot,
                    state["channel_id"]
                )

                if channel is None:
                    continue

                message=await channel.send(
                    embed=relicembed(
                        mod,
                        state
                    ),
                    view=mod.RelicView(
                        self.bot
                    )
                )

                mod.message(
                    game_id,
                    message.id
                )

                fresh=mod.get(
                    game_id
                )

                if (
                    fresh is None
                    or fresh["message_id"]
                    !=message.id
                ):
                    try:
                        await message.delete(
                            reason=(
                                "relic repost "
                                "activation failed"
                            )
                        )

                    except discord.HTTPException:
                        pass

                    raise RuntimeError(
                        "new relic panel "
                        "did not become active"
                    )

                await disable_old_relic(
                    self.bot,
                    mod,
                    state,
                    message.id
                )

                mark(
                    "relic",
                    game_id,
                    today,
                    message.id
                )

            except Exception as error:
                if message is not None:
                    try:
                        fresh=mod.get(
                            state["id"]
                        )

                        if (
                            fresh is None
                            or fresh["message_id"]
                            !=message.id
                        ):
                            await message.delete(
                                reason=(
                                    "failed relic "
                                    "daily repost"
                                )
                            )

                    except Exception:
                        pass

                print(
                    f"relic daily repost "
                    f"game {state.get('id','?')}: "
                    f"{type(error).__name__}: "
                    f"{error}"
                )

    @tasks.loop(minutes=1)
    async def loop(self):
        now=core.now()

        today=now.date().isoformat()

        minute=(
            now.hour*60
            +now.minute
        )

        if minute>=1:
            await self.sins(
                today
            )

        if minute>=2:
            await self.relics(
                today
            )

    @loop.before_loop
    async def ready(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    init()

    await bot.add_cog(
        EventReposts(bot)
    )
