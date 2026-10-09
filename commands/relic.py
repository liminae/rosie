import asyncio
import sqlite3
import time
import random

import discord
from core import database
from core import game as core
from core import seasonal
from discord import app_commands
from discord.ext import commands,tasks
from discord.http import Route
from core import policy
from core import emoji as rosieemoji

REVENGE=300
COOLDOWN=600
BASE=5500
ROSES=45
RING=350
REMINDER=600
TEST_MARGIN=0.05
TEST_RANDOM_MAX=100*60
TEST_RANDOM_STOP=60*60

def connect():
    con=sqlite3.connect(
        database.FILE
    )
    con.row_factory=sqlite3.Row
    return con

def init():
    with connect() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS relic_games(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER,
                active INTEGER NOT NULL DEFAULT 1,
                days INTEGER NOT NULL,
                cooldown REAL NOT NULL,
                reward_roses INTEGER NOT NULL,
                reward_rings INTEGER NOT NULL,
                started_at REAL NOT NULL,
                ends_at REAL NOT NULL,
                holder_id INTEGER,
                previous_holder_id INTEGER,
                holder_since REAL,
                steals INTEGER NOT NULL DEFAULT 0,
                winner_id INTEGER,
                rewarded INTEGER NOT NULL DEFAULT 0,
                ended_at REAL
            )"""
        )

        cols={
            row[1]
            for row in con.execute(
                "PRAGMA table_info(relic_games)"
            )
        }

        if "dynamic" not in cols:
            con.execute(
                "ALTER TABLE relic_games "
                "ADD COLUMN dynamic INTEGER NOT NULL DEFAULT 0"
            )

        if "testing" not in cols:
            con.execute(
                "ALTER TABLE relic_games "
                "ADD COLUMN testing INTEGER NOT NULL DEFAULT 0"
            )

        if "reminded" not in cols:
            con.execute(
                "ALTER TABLE relic_games "
                "ADD COLUMN reminded INTEGER NOT NULL DEFAULT 0"
            )

        con.execute(
            """CREATE TABLE IF NOT EXISTS relic_players(
                game_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                steals INTEGER NOT NULL DEFAULT 0,
                last_steal_at REAL,
                PRIMARY KEY(game_id,user_id)
            )"""
        )

        con.execute(
            """CREATE TABLE IF NOT EXISTS relic_test(
                slot INTEGER PRIMARY KEY,
                game_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                armed_at REAL NOT NULL
            )"""
        )

def row(found):
    return dict(found) if found else None

def arm(
    game_id,
    user_id
):
    with connect() as con:
        con.execute(
            """INSERT OR REPLACE INTO relic_test(
                slot,
                game_id,
                user_id,
                armed_at
            ) VALUES(1,?,?,?)""",
            (
                game_id,
                user_id,
                time.time()
            )
        )

def armed(
    game_id=None
):
    with connect() as con:
        if game_id is None:
            found=con.execute(
                "SELECT * FROM relic_test WHERE slot=1"
            ).fetchone()
        else:
            found=con.execute(
                """SELECT * FROM relic_test
                WHERE slot=1
                AND game_id=?""",
                (game_id,)
            ).fetchone()

    return row(found)

def clear(
    game_id=None
):
    with connect() as con:
        if game_id is None:
            con.execute(
                "DELETE FROM relic_test WHERE slot=1"
            )
        else:
            con.execute(
                """DELETE FROM relic_test
                WHERE slot=1
                AND game_id=?""",
                (game_id,)
            )

def testready(
    game,
    user_id
):
    if game["holder_id"]==user_id:
        return None

    ready=0

    with connect() as con:
        player=con.execute(
            """SELECT last_steal_at
            FROM relic_players
            WHERE game_id=?
            AND user_id=?""",
            (
                game["id"],
                user_id
            )
        ).fetchone()

    if (
        player
        and player["last_steal_at"] is not None
    ):
        ready=max(
            ready,
            float(player["last_steal_at"])
            +float(game["cooldown"])
        )

    if (
        game["previous_holder_id"]==user_id
        and game["holder_since"] is not None
    ):
        revenge=(
            5
            if game["testing"]
            else REVENGE
        )

        ready=max(
            ready,
            float(game["holder_since"])
            +revenge
        )

    return ready

def active(guild_id):
    with connect() as con:
        found=con.execute(
            """SELECT *
            FROM relic_games
            WHERE guild_id=?
            AND active=1
            ORDER BY id DESC
            LIMIT 1""",
            (guild_id,)
        ).fetchone()

    return row(found)

def games():
    with connect() as con:
        rows=con.execute(
            """SELECT *
            FROM relic_games
            WHERE active=1
            ORDER BY id"""
        ).fetchall()

    return [
        dict(found)
        for found in rows
    ]

def get(game_id):
    with connect() as con:
        found=con.execute(
            "SELECT * FROM relic_games WHERE id=?",
            (game_id,)
        ).fetchone()

    return row(found)

def players(game_id):
    with connect() as con:
        found=con.execute(
            """SELECT user_id
            FROM relic_players
            WHERE game_id=?
            ORDER BY user_id""",
            (game_id,)
        ).fetchall()

    return [
        int(user["user_id"])
        for user in found
    ]

def reminded(game_id):
    with connect() as con:
        con.execute(
            """UPDATE relic_games
            SET reminded=1
            WHERE id=?""",
            (game_id,)
        )

def growing(steals):
    steals=max(
        0,
        int(steals)
    )

    return (
        BASE+steals*ROSES,
        steals//RING
    )

def reprice(game_id):
    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        found=con.execute(
            """SELECT *
            FROM relic_games
            WHERE id=?""",
            (game_id,)
        ).fetchone()

        if found is None:
            return None

        roses,rings=growing(
            found["steals"]
        )

        con.execute(
            """UPDATE relic_games
            SET reward_roses=?,
                reward_rings=?
            WHERE id=?""",
            (
                roses,
                rings,
                game_id
            )
        )

        current=con.execute(
            """SELECT *
            FROM relic_games
            WHERE id=?""",
            (game_id,)
        ).fetchone()

    return dict(current)

def create(
    guild_id,
    channel_id,
    days,
    testing=False
):
    now=time.time()

    cooldown=(
        5
        if testing
        else COOLDOWN
    )

    ends=(
        now+600
        if testing
        else now+days*86400
    )

    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        if con.execute(
            """SELECT 1
            FROM relic_games
            WHERE guild_id=?
            AND active=1""",
            (guild_id,)
        ).fetchone():
            return None

        cur=con.execute(
            """INSERT INTO relic_games(
                guild_id,
                channel_id,
                days,
                cooldown,
                reward_roses,
                reward_rings,
                started_at,
                ends_at,
                dynamic,
                testing
            ) VALUES(?,?,?,?,?,?,?,?,1,?)""",
            (
                guild_id,
                channel_id,
                days,
                cooldown,
                BASE,
                0,
                now,
                ends,
                int(testing)
            )
        )

        return cur.lastrowid

def message(
    game_id,
    message_id
):
    with connect() as con:
        con.execute(
            """UPDATE relic_games
            SET message_id=?
            WHERE id=?""",
            (
                message_id,
                game_id
            )
        )

def repost(
    game_id,
    channel_id,
    message_id
):
    with connect() as con:
        con.execute(
            """UPDATE relic_games
            SET channel_id=?,
                message_id=?
            WHERE id=?""",
            (
                channel_id,
                message_id,
                game_id
            )
        )

def cancel(game_id):
    with connect() as con:
        con.execute(
            """UPDATE relic_games
            SET active=0,
                ended_at=?
            WHERE id=?
            AND active=1""",
            (
                time.time(),
                game_id
            )
        )

        con.execute(
            "DELETE FROM relic_test WHERE game_id=?",
            (game_id,)
        )

def steal(
    game_id,
    user_id
):
    now=time.time()

    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        game=con.execute(
            "SELECT * FROM relic_games WHERE id=?",
            (game_id,)
        ).fetchone()

        if (
            game is None
            or not game["active"]
        ):
            return {
                "ok":False,
                "reason":"dead"
            }

        if now>=game["ends_at"]:
            return {
                "ok":False,
                "reason":"ended"
            }

        if game["holder_id"]==user_id:
            return {
                "ok":False,
                "reason":"holder"
            }

        player=con.execute(
            """SELECT last_steal_at
            FROM relic_players
            WHERE game_id=?
            AND user_id=?""",
            (
                game_id,
                user_id
            )
        ).fetchone()

        if (
            player
            and player["last_steal_at"]
            is not None
        ):
            ready=(
                player["last_steal_at"]
                +game["cooldown"]
            )

            if now<ready:
                return {
                    "ok":False,
                    "reason":"cooldown",
                    "ready":ready
                }

        if (
            game["previous_holder_id"]
            ==user_id
            and game["holder_since"]
            is not None
        ):
            revenge=(
                5
                if game["testing"]
                else REVENGE
            )

            ready=(
                game["holder_since"]
                +revenge
            )

            if now<ready:
                return {
                    "ok":False,
                    "reason":"revenge",
                    "ready":ready
                }

        previous=game[
            "holder_id"
        ]

        takeover=previous is not None

        con.execute(
            """INSERT INTO relic_players(
                game_id,
                user_id,
                steals,
                last_steal_at
            )
            VALUES(?,?,?,?)
            ON CONFLICT(game_id,user_id)
            DO UPDATE SET
                steals=steals+excluded.steals,
                last_steal_at=COALESCE(
                    excluded.last_steal_at,
                    last_steal_at
                )""",
            (
                game_id,
                user_id,
                int(takeover),
                now if takeover else None
            )
        )

        steals=(
            int(game["steals"])
            +int(takeover)
        )

        roses,rings=growing(
            steals
        )

        con.execute(
            """UPDATE relic_games
            SET previous_holder_id=?,
                holder_id=?,
                holder_since=?,
                steals=?,
                reward_roses=?,
                reward_rings=?
            WHERE id=?""",
            (
                previous,
                user_id,
                now,
                steals,
                roses,
                rings,
                game_id
            )
        )

        return {
            "ok":True,
            "previous":previous,
            "takeover":takeover
        }

def settle(game_id):
    now=time.time()

    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        game=con.execute(
            "SELECT * FROM relic_games WHERE id=?",
            (game_id,)
        ).fetchone()

        if game is None:
            return None

        if not game["active"]:
            return dict(game)

        if now<game["ends_at"]:
            return None

        winner=game[
            "holder_id"
        ]

        if (
            winner is not None
            and not game["testing"]
        ):
            con.execute(
                """INSERT OR IGNORE
                INTO wallets(guild_id,user_id)
                VALUES(?,?)""",
                (
                    game["guild_id"],
                    winner
                )
            )

            con.execute(
                """UPDATE wallets
                SET roses=roses+?,
                    rings=rings+?
                WHERE guild_id=?
                AND user_id=?""",
                (
                    game["reward_roses"],
                    game["reward_rings"],
                    game["guild_id"],
                    winner
                )
            )

        con.execute(
            """UPDATE relic_games
            SET active=0,
                winner_id=?,
                rewarded=1,
                ended_at=?
            WHERE id=?""",
            (
                winner,
                now,
                game_id
            )
        )

        con.execute(
            "DELETE FROM relic_test WHERE game_id=?",
            (game_id,)
        )

        return dict(
            con.execute(
                "SELECT * FROM relic_games WHERE id=?",
                (game_id,)
            ).fetchone()
        )

def cool(seconds):
    if seconds==5:
        return "5 seconds"

    if seconds==300:
        return "5 minutes"

    if seconds==600:
        return "10 minutes"

    if seconds==1200:
        return "20 minutes"

    return f"{int(seconds)} seconds"

def progress(game):
    return "\n".join(
        [
            f'starts at ⊹ {BASE:,} roses {rosieemoji.ROSE}',
            f'each steal ⊹ +{ROSES:,} roses {rosieemoji.ROSE}',
            f"every {RING:,} steals ⊹ +1 ring 💍"
        ]
    )


def pot(game):
    lines=[
        f"⊹ {game['reward_roses']:,} roses {rosieemoji.ROSE}"
    ]

    if game["reward_rings"]:
        lines.append(
            f"⊹ {game['reward_rings']:,} "
            f"{'ring' if game['reward_rings']==1 else 'rings'} 💍"
        )

    return "\n".join(
        lines
    )

def rules():
    return discord.Embed(
        title="🥀 relic",
        description=(
            f'steal it. every real steal grows the pot. whoever holds it when time dies wins.\n\nstarting pot ⊹ **{BASE:,} roses {rosieemoji.ROSE}**\nevery takeover ⊹ **+{ROSES:,} roses {rosieemoji.ROSE}**\nevery {RING:,} steals ⊹ **+1 ring 💍**\ncooldown ⊹ **{cool(COOLDOWN)}**'        ),
        color=discord.Color.dark_red()
    )

def embed(game):
    if game["holder_id"] is None:
        holder="nobody yet"
        held="waiting"
    else:
        holder=(
            f"<@{game['holder_id']}>"
        )

        held=(
            f"<t:{int(game['holder_since'])}:R>"
        )

    growth=progress(
        game
    )

    extra=(
        f"\n{growth}"
        if growth
        else ""
    )

    out=discord.Embed(
        title="🥀 relic",
        description=(
            f"holder ⊹ {holder}\n"
            f"held ⊹ {held}\n"
            f"stolen ⊹ **{game['steals']:,} times**\n"
            f"cooldown ⊹ **{cool(game['cooldown'])}**\n\n"

            f"**pot**\n"
            f"{pot(game)}"
            f"{extra}\n\n"

            f"ends ⊹ "
            f"<t:{int(game['ends_at'])}:R>"
        ),
        color=discord.Color.dark_red()
    )

    if game.get(
        "testing"
    ):
        out.set_footer(
            text="testing mode"
        )

    return out

def over(game):
    stats=(
        f"stolen ⊹ "
        f"**{game['steals']:,} times**"
    )

    if game.get(
        "testing"
    ):
        if game["winner_id"] is None:
            text=(
                f"{stats}\n\n"
                "testing mode"
            )
        else:
            text=(
                f"{stats}\n\n"
                f"<@{game['winner_id']}> "
                "kept the test relic\n"
                "testing mode"
            )

    elif game["winner_id"] is None:
        text=(
            f"{stats}\n\n"
            "nobody touched it\n"
            "nothing paid out"
        )

    else:
        text=(
            f"{stats}\n\n"
            f"<@{game['winner_id']}> "
            f"kept the relic\n"
            f"{pot(game)}"
        )

    out=discord.Embed(
        title="🥀 relic",
        description=text,
        color=discord.Color.dark_red()
    )

    if game.get(
        "testing"
    ):
        out.set_footer(
            text="testing mode"
        )

    return out

def stopped(
    testing=False
):
    out=discord.Embed(
        title="🥀 relic",
        description=(
            "game canceled\n"
            "nothing paid out"
        ),
        color=discord.Color.dark_red()
    )

    if testing:
        out.set_footer(
            text="testing mode"
        )

    return out

class RelicView(discord.ui.View):
    def __init__(
        self,
        bot,
        disabled=False
    ):
        super().__init__(
            timeout=None
        )

        self.bot=bot

        if disabled:
            for item in self.children:
                item.disabled=True

    def game(
        self,
        it
    ):
        game=active(
            it.guild.id
        )

        if (
            game is None
            or game["message_id"]
            !=it.message.id
        ):
            return None

        return game

    @discord.ui.button(
        emoji="🫳",
        style=discord.ButtonStyle.danger,
        custom_id="rosie:relic:steal"
    )
    async def steal_button(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        game=self.game(
            it
        )

        if game is None:
            await it.response.send_message(
                "this relic is dead",
                ephemeral=True
            )
            return

        result=steal(
            game["id"],
            it.user.id
        )

        if not result["ok"]:
            if result["reason"]=="cooldown":
                await it.response.send_message(
                    (
                        "not yet babe\n"
                        f"ready ⊹ "
                        f"<t:{int(result['ready'])}:R>"
                    ),
                    ephemeral=True
                )

            elif result["reason"]=="revenge":
                await it.response.send_message(
                    (
                        "no instant takebacks\n"
                        f"ready ⊹ "
                        f"<t:{int(result['ready'])}:R>"
                    ),
                    ephemeral=True
                )

            elif result["reason"]=="holder":
                await it.response.send_message(
                    "u literally have it",
                    ephemeral=True
                )

            elif result["reason"]=="ended":
                done=settle(
                    game["id"]
                )

                await it.response.edit_message(
                    embed=over(done),
                    view=RelicView(
                        self.bot,
                        True
                    )
                )

            else:
                await it.response.send_message(
                    "this relic is dead",
                    ephemeral=True
                )

            return

        current=get(
            game["id"]
        )

        if not current.get(
            "testing"
        ):
            core.touch(
                it.user.id
            )

            seasonal.commandxp(
                it.user.id,
                "relic"
            )

        await it.response.edit_message(
            embed=embed(current),
            view=self
        )

class Relic(commands.Cog):
    def __init__(
        self,
        bot
    ):
        self.bot=bot
        self.managed=False
        self.shot=None
        self.clock.start()

    async def registry(self):
        if self.managed:
            return

        app_id=(
            self.bot.application_id
            or self.bot.user.id
        )

        await self.bot.http.request(
            Route(
                "POST",
                "/applications/{application_id}/commands",
                application_id=app_id
            ),
            json={
                "name":"relic",
                "description":"steal the relic",
                "type":1,
                "options":[
                    {
                        "name":"action",
                        "description":'action',
                        "type":3,
                        "required":False,
                        "choices":[
                            {
                                "name":"start",
                                "value":"start"
                            },
                            {
                                "name":"stop",
                                "value":"stop"
                            }
                        ]
                    },
                    {
                        "name":"days",
                        "description":'days',
                        "type":4,
                        "required":False,
                        "min_value":1
                    }
                ]
            }
        )

        self.managed=True

        print(
            "relic command registry ✓"
        )

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            await self.registry()

        except Exception as error:
            print(
                f"relic registry failed ⊹ "
                f"{error}"
            )

        for game in games():
            current=reprice(
                game["id"]
            )

            if (
                current is None
                or not current["message_id"]
            ):
                continue

            try:
                channel=(
                    self.bot.get_channel(
                        current["channel_id"]
                    )
                    or await self.bot.fetch_channel(
                        current["channel_id"]
                    )
                )

                msg=await channel.fetch_message(
                    current["message_id"]
                )

                await msg.edit(
                    embed=embed(
                        current
                    ),
                    view=RelicView(
                        self.bot
                    )
                )

                print(
                    f"relic refreshed ⊹ game {current['id']} "
                    f"⊹ {current['reward_roses']:,} roses "
                    f"⊹ {current['reward_rings']} rings"
                )

            except discord.HTTPException as error:
                print(
                    f"relic refresh panel failed ⊹ "
                    f"game {current['id']} ⊹ {error}"
                )

        shot=armed()

        if shot is not None:
            game=get(
                shot["game_id"]
            )

            if (
                game is not None
                and game["active"]
                and game["ends_at"]>time.time()
            ):
                self.queue(
                    game,
                    shot["user_id"]
                )
            else:
                clear(
                    shot["game_id"]
                )

    def cog_unload(self):
        self.clock.cancel()

        if (
            self.shot is not None
            and not self.shot.done()
        ):
            self.shot.cancel()

    def queue(
        self,
        game,
        user_id
    ):
        if (
            self.shot is not None
            and not self.shot.done()
        ):
            self.shot.cancel()

        self.shot=asyncio.create_task(
            self.fire(
                game,
                user_id
            )
        )

    def unqueue(self):
        if (
            self.shot is not None
            and not self.shot.done()
        ):
            self.shot.cancel()

        self.shot=None

    async def refresh(
        self,
        game
    ):
        if (
            game is None
            or not game.get("active")
            or not game.get("message_id")
        ):
            return

        try:
            channel=(
                self.bot.get_channel(
                    game["channel_id"]
                )
                or await self.bot.fetch_channel(
                    game["channel_id"]
                )
            )

            msg=await channel.fetch_message(
                game["message_id"]
            )

            await msg.edit(
                embed=embed(game),
                view=RelicView(
                    self.bot
                )
            )

        except discord.HTTPException:
            pass

    async def randomfire(
        self,
        game,
        user_id
    ):
        cutoff=(
            float(game["ends_at"])
            -TEST_RANDOM_STOP
        )

        while time.time()<cutoff:
            shot=armed(
                game["id"]
            )

            if (
                shot is None
                or shot["user_id"]!=user_id
            ):
                return False

            current=get(
                game["id"]
            )

            if (
                current is None
                or not current["active"]
            ):
                clear(
                    game["id"]
                )
                return False

            now=time.time()
            ready=testready(
                current,
                user_id
            )

            if ready is None:
                await asyncio.sleep(
                    min(
                        5,
                        max(0,cutoff-now)
                    )
                )
                continue

            if ready>now:
                await asyncio.sleep(
                    min(
                        ready-now,
                        max(0,cutoff-now)
                    )
                )
                continue

            delay=random.uniform(
                0,
                TEST_RANDOM_MAX
            )

            if now+delay>=cutoff:
                await asyncio.sleep(
                    max(0,cutoff-now)
                )
                break

            await asyncio.sleep(
                delay
            )

            shot=armed(
                game["id"]
            )

            if (
                shot is None
                or shot["user_id"]!=user_id
            ):
                return False

            current=get(
                game["id"]
            )

            if (
                current is None
                or not current["active"]
            ):
                clear(
                    game["id"]
                )
                return False

            ready=testready(
                current,
                user_id
            )

            if (
                ready is None
                or ready>time.time()
            ):
                continue

            result=steal(
                game["id"],
                user_id
            )

            if result["ok"]:
                core.touch(
                    user_id
                )

                current=get(
                    game["id"]
                )

                await self.refresh(
                    current
                )

                print(
                    f"relic test random hit ⊹ "
                    f"game {game['id']} ⊹ "
                    f"user {user_id}"
                )

            elif result["reason"] in (
                "dead",
                "ended"
            ):
                clear(
                    game["id"]
                )
                return False

        return True

    async def fire(
        self,
        game,
        user_id
    ):
        target=(
            float(game["ends_at"])
            -TEST_MARGIN
        )

        try:
            keep=await self.randomfire(
                game,
                user_id
            )

            if not keep:
                return

            delay=(
                target
                -time.time()
            )

            if delay>0.02:
                await asyncio.sleep(
                    delay-0.01
                )

            while time.time()<target:
                await asyncio.sleep(0)

        except asyncio.CancelledError:
            return

        shot=armed(
            game["id"]
        )

        if (
            shot is None
            or shot["user_id"]!=user_id
        ):
            return

        current=get(
            game["id"]
        )

        if (
            current is None
            or not current["active"]
        ):
            clear(
                game["id"]
            )
            return

        if current["holder_id"]==user_id:
            result={
                "ok":True,
                "reason":"holder"
            }
        else:
            result=steal(
                game["id"],
                user_id
            )

        clear(
            game["id"]
        )

        if (
            result["ok"]
            and result.get("reason")!="holder"
        ):
            core.touch(
                user_id
            )

        user=self.bot.get_user(
            user_id
        )

        if user is None:
            try:
                user=await self.bot.fetch_user(
                    user_id
                )
            except discord.HTTPException:
                user=None

        if user is not None:
            if result["ok"]:
                text=(
                    "test hit ⊹ **already holding**"
                    if result.get("reason")=="holder"
                    else "test hit ⊹ **relic stolen**"
                )
            elif result["reason"] in (
                "cooldown",
                "revenge"
            ):
                text=(
                    "test missed ⊹ **not ready**\n"
                    f"ready ⊹ "
                    f"<t:{int(result['ready'])}:R>"
                )
            else:
                text=(
                    "test missed ⊹ **"
                    f"{result['reason']}**"
                )

            try:
                await user.send(
                    text
                )
            except discord.HTTPException:
                pass

        delay=(
            float(game["ends_at"])
            -time.time()
        )

        if delay>0:
            await asyncio.sleep(
                delay
            )

        done=settle(
            game["id"]
        )

        if done is not None:
            await self.close(
                done
            )

    async def remind(
        self,
        game
    ):
        ids=set(
            players(
                game["id"]
            )
        )

        if game["holder_id"] is not None:
            ids.add(
                int(game["holder_id"])
            )

        if not ids:
            reminded(
                game["id"]
            )
            return

        url=(
            "https://discord.com/channels/"
            f"{game['guild_id']}/"
            f"{game['channel_id']}/"
            f"{game['message_id']}"
            if game["message_id"]
            else None
        )

        text=(
            "🥀 relic ends in **10 minutes**\n"
            f"{pot(game)}\n"
            f"ends ⊹ <t:{int(game['ends_at'])}:R>"
        )

        if url:
            text+=(
                "\nsteal it ⊹ "
                f"{url}"
            )

        sent=0

        for user_id in ids:
            user=self.bot.get_user(
                user_id
            )

            if user is None:
                try:
                    user=await self.bot.fetch_user(
                        user_id
                    )
                except discord.HTTPException:
                    user=None

            if user is None:
                continue

            try:
                await user.send(
                    text
                )
                sent+=1
            except discord.HTTPException:
                pass

        reminded(
            game["id"]
        )

        print(
            f"relic reminder ⊹ game {game['id']} "
            f"⊹ {sent}/{len(ids)} dms"
        )

    async def manage(
        self,
        it
    ):
        return (
            policy.haspermission(it.user,"administrator")
            or await self.bot.is_owner(
                it.user
            )
        )

    async def close(
        self,
        game
    ):
        if (
            game is None
            or not game["message_id"]
        ):
            return

        try:
            channel=(
                self.bot.get_channel(
                    game["channel_id"]
                )
                or await self.bot.fetch_channel(
                    game["channel_id"]
                )
            )

            msg=await channel.fetch_message(
                game["message_id"]
            )

            await msg.edit(
                embed=over(game),
                view=RelicView(
                    self.bot,
                    True
                )
            )

        except discord.HTTPException:
            pass

    @tasks.loop(
        seconds=1
    )
    async def clock(self):
        now=time.time()

        for game in games():
            left=(
                float(game["ends_at"])
                -now
            )

            if (
                not game.get("testing")
                and not game.get("reminded")
                and 0<left<=REMINDER
            ):
                await self.remind(
                    game
                )

            if left<=0:
                done=settle(
                    game["id"]
                )

                await self.close(
                    done
                )

    @clock.before_loop
    async def ready(self):
        await self.bot.wait_until_ready()

    @app_commands.command(
        name="relic",
        description="steal the relic"
    )
    @app_commands.guild_only()
    @app_commands.choices(
        action=[
            app_commands.Choice(
                name="start",
                value="start"
            ),
            app_commands.Choice(
                name="stop",
                value="stop"
            )
        ]
    )
    async def relic(
        self,
        it:discord.Interaction,
        action:str|None=None,
        days:int|None=None
    ):
        if action is None:
            if days is not None:
                await it.response.send_message(
                    "days only works with start",
                    ephemeral=True
                )
                return

            await it.response.send_message(
                embed=rules()
            )
            return

        if not await self.manage(
            it
        ):
            await it.response.send_message(
                "nuh uh",
                ephemeral=True
            )
            return

        if action=="start":
            if days is None:
                await it.response.send_message(
                    "pick number of days",
                    ephemeral=True
                )
                return

            if days<1:
                await it.response.send_message(
                    "days has to be at least 1",
                    ephemeral=True
                )
                return

            if active(
                it.guild.id
            ):
                await it.response.send_message(
                    "relic already running",
                    ephemeral=True
                )
                return

            game_id=create(
                it.guild.id,
                it.channel.id,
                days
            )

            if game_id is None:
                await it.response.send_message(
                    "relic already running",
                    ephemeral=True
                )
                return

            game=get(
                game_id
            )

            await it.response.send_message(
                embed=embed(
                    game
                ),
                view=RelicView(
                    self.bot
                )
            )

            msg=await it.original_response()

            message(
                game_id,
                msg.id
            )

            return

        if days is not None:
            await it.response.send_message(
                "days only works with start",
                ephemeral=True
            )
            return

        game=active(
            it.guild.id
        )

        if game is None:
            await it.response.send_message(
                "no relic rn",
                ephemeral=True
            )
            return

        cancel(
            game["id"]
        )

        if game["message_id"]:
            try:
                channel=(
                    self.bot.get_channel(
                        game["channel_id"]
                    )
                    or await self.bot.fetch_channel(
                        game["channel_id"]
                    )
                )

                msg=await channel.fetch_message(
                    game["message_id"]
                )

                await msg.edit(
                    embed=stopped(
                        bool(
                            game.get(
                                "testing"
                            )
                        )
                    ),
                    view=RelicView(
                        self.bot,
                        True
                    )
                )

            except discord.HTTPException:
                pass

        await it.response.send_message(
            "relic stopped",
            ephemeral=True
        )

async def setup(bot):
    init()

    bot.add_view(
        RelicView(bot)
    )

    await bot.add_cog(
        Relic(bot)
    )
