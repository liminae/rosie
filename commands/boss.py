from collections import deque
from pathlib import Path
import secrets
import sqlite3
import time

import discord
from core import database
from core import guildconfig
from core import legacyconfig
from core import petbuff
from discord import app_commands
from discord.ext import commands,tasks
from discord.http import Route
from core import emoji as rosieemoji


DURATION=300
COOLDOWN=30
AUTO_COOLDOWN=7200

TEST_DURATION=120
TEST_COOLDOWN=3
TEST_ROUND=8

BURST=120
GAP=45
NEEDED=12
USERS=3

ROUND=30
PHASE_CAP=1150
MAX_HP=7119
POT=7119

XASG_HP=4875
XASG_POT=4875

ASSETS=(
    Path(__file__).resolve()
    .parents[1]
    /"assets"
    /"boss"
)

RECENT={}
_petbuff_patch=True

def spawnconfig(guild):
    data=guildconfig.get(
        guild.id
    )

    legacy_id=legacyconfig.BOSS_CHANNEL_ID

    legacy=(
        legacy_id
        if (
            legacy_id
            and guild.get_channel(
                legacy_id
            ) is not None
        )
        else None
    )

    if data is not None:
        channel_id=data[
            "boss_channel_id"
        ]

        automatic=data[
            "boss_auto_enabled"
        ]

        if channel_id is not None:
            return (
                channel_id,
                bool(automatic)
            )

        if (
            automatic is not None
            and legacy is not None
        ):
            return (
                legacy,
                bool(automatic)
            )

    if legacy is not None:
        return (
            legacy,
            True
        )

    return (
        None,
        False
    )

MIMIC_TELLS=(
    (
        "“come closer.”",
        "the lid opens much too slowly.",
        ("guard",),
        "normal"
    ),
    (
        "“i don't bite.”",
        "its teeth disappear behind a crooked smile.",
        ("guard",),
        "normal"
    ),
    (
        "“mine.”",
        "the ribbon tightens like a muscle.",
        ("strike",),
        "normal"
    ),
    (
        "“don't touch me.”",
        "the hinges snap forward.",
        ("strike",),
        "normal"
    ),
    (
        "“pretty, isn't it?”",
        "something gold catches the light behind its teeth.",
        ("reckless",),
        "normal"
    ),
    (
        "“scared?”",
        "its tongue retreats, leaving something shiny behind.",
        ("reckless",),
        "normal"
    )
)

XASG_TELLS=(
    (
        "“kneel.”",
        "he swings his sword in a wide arc.",
        ("guard",),
        "normal"
    ),
    (
        "“mortal.”",
        "his blade whistles toward you.",
        ("guard",),
        "normal"
    ),
    (
        "he rises higher.",
        "for a moment, his guard is completely open.",
        ("strike",),
        "normal"
    ),
    (
        "his sword lowers.",
        "he looks away for half a second.",
        ("strike",),
        "normal"
    ),
    (
        "the sun catches his wings.",
        "feathers begin to burn.",
        ("strike","reckless"),
        "burning"
    ),
    (
        "smoke trails behind him.",
        "burned feathers peel away in the wind.",
        ("strike","reckless"),
        "burning"
    )
)

BOSSES={
    "mimic":{
        "title":"🎁 the mimic",
        "art":ASSETS/"mimic.png",
        "intro":None,
        "tells":MIMIC_TELLS,
        "hp":MAX_HP,
        "reward":POT,
        "fixed_loot":False
    },
    "xasg":{
        "title":"🪽 xasg the risen",
        "art":ASSETS/"xasg.png",
        "intro":(
            "mortal xasg rises above the clouds "
            "with a surge of power."
        ),
        "tells":XASG_TELLS,
        "hp":XASG_HP,
        "reward":XASG_POT,
        "fixed_loot":True
    }
}

NATURAL_BOSSES=(
    "mimic",
    "xasg"
)

def connect():
    con=sqlite3.connect(
        database.FILE,
        timeout=10
    )
    con.row_factory=sqlite3.Row
    return con

def init():
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS boss_games(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            message_id INTEGER,
            name TEXT NOT NULL,
            hp INTEGER NOT NULL,
            max_hp INTEGER NOT NULL,
            reward_roses INTEGER NOT NULL,
            started_at REAL NOT NULL,
            ends_at REAL NOT NULL,
            tell_idx INTEGER NOT NULL,
            tell_at REAL NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            result TEXT,
            mvp_id INTEGER,
            ended_at REAL
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS boss_players(
            game_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            damage INTEGER NOT NULL DEFAULT 0,
            actions INTEGER NOT NULL DEFAULT 0,
            last_action REAL NOT NULL DEFAULT 0,
            reward INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(game_id,user_id)
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS boss_users(
            user_id INTEGER PRIMARY KEY,
            defeats INTEGER NOT NULL DEFAULT 0,
            damage INTEGER NOT NULL DEFAULT 0,
            mvps INTEGER NOT NULL DEFAULT 0
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS boss_spawn(
            guild_id INTEGER PRIMARY KEY,
            last_auto REAL NOT NULL DEFAULT 0
        )""")

        cols={
            row[1]
            for row in con.execute(
                "PRAGMA table_info(boss_games)"
            )
        }

        for name,sql in (
            (
                "phase_damage",
                "INTEGER NOT NULL DEFAULT 0"
            ),
            (
                "meaningful_actions",
                "INTEGER NOT NULL DEFAULT 0"
            ),
            (
                "correct_actions",
                "INTEGER NOT NULL DEFAULT 0"
            ),
            (
                "paid_roses",
                "INTEGER NOT NULL DEFAULT 0"
            ),
            (
                "testing",
                "INTEGER NOT NULL DEFAULT 0"
            )
        ):
            if name not in cols:
                con.execute(
                    f"ALTER TABLE boss_games "
                    f"ADD COLUMN {name} {sql}"
                )

def row(found):
    return (
        dict(found)
        if found
        else None
    )

def testing(game):
    return bool(
        game.get(
            "testing",
            0
        )
    )

def config(game):
    return BOSSES.get(
        game.get("name"),
        BOSSES["mimic"]
    )

def title(game):
    return config(
        game
    )["title"]

def art(game):
    path=config(
        game
    )["art"]

    if path.exists():
        return path

    return BOSSES[
        "mimic"
    ]["art"]

def roundtime(game):
    return (
        TEST_ROUND
        if testing(game)
        else ROUND
    )

def actioncd(game):
    return (
        TEST_COOLDOWN
        if testing(game)
        else COOLDOWN
    )

def active(
    guild_id,
    include_testing=False
):
    clause=(
        "active!=0"
        if include_testing
        else "active=1"
    )

    with connect() as con:
        found=con.execute(
            f"""SELECT *
            FROM boss_games
            WHERE guild_id=?
            AND {clause}
            ORDER BY id DESC
            LIMIT 1""",
            (guild_id,)
        ).fetchone()

    return row(found)

def get(game_id):
    with connect() as con:
        found=con.execute(
            """SELECT *
            FROM boss_games
            WHERE id=?""",
            (game_id,)
        ).fetchone()

    return row(found)

def players(game_id):
    with connect() as con:
        rows=con.execute(
            """SELECT *
            FROM boss_players
            WHERE game_id=?
            ORDER BY damage DESC,user_id""",
            (game_id,)
        ).fetchall()

    return [
        dict(item)
        for item in rows
    ]

def note(
    guild_id,
    user_id,
    now=None
):
    now=now or time.time()

    q=RECENT.setdefault(
        guild_id,
        deque()
    )

    if (
        q
        and now-q[-1][0]>GAP
    ):
        q.clear()

    while (
        q
        and q[0][0]<now-BURST
    ):
        q.popleft()

    q.append(
        (
            now,
            user_id
        )
    )

    return (
        len(q),
        len({
            uid
            for _,uid in q
        })
    )

def ready(
    guild_id,
    now=None
):
    now=now or time.time()

    with connect() as con:
        found=con.execute(
            """SELECT last_auto
            FROM boss_spawn
            WHERE guild_id=?""",
            (guild_id,)
        ).fetchone()

    last=(
        found["last_auto"]
        if found
        else 0
    )

    return (
        now>=last+AUTO_COOLDOWN
    )

def tell(game):
    tells=config(
        game
    )["tells"]

    return tells[
        game["tell_idx"]
        %len(tells)
    ]

def choose():
    return NATURAL_BOSSES[
        secrets.randbelow(
            len(NATURAL_BOSSES)
        )
    ]

def create(
    guild_id,
    channel_id,
    automatic=False,
    test=False,
    boss_name=None
):
    now=time.time()

    if boss_name is None:
        boss_name=(
            choose()
            if automatic
            else "mimic"
        )

    if boss_name not in BOSSES:
        raise ValueError(
            "invalid boss"
        )

    duration=(
        TEST_DURATION
        if test
        else DURATION
    )

    cfg=BOSSES[
        boss_name
    ]

    tells=cfg[
        "tells"
    ]

    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        if automatic:
            found=con.execute(
                """SELECT last_auto
                FROM boss_spawn
                WHERE guild_id=?""",
                (guild_id,)
            ).fetchone()

            last=(
                found["last_auto"]
                if found
                else 0
            )

            if (
                now
                <last+AUTO_COOLDOWN
            ):
                return None

        old=con.execute(
            """SELECT *
            FROM boss_games
            WHERE guild_id=?
            AND active!=0
            ORDER BY id DESC
            LIMIT 1""",
            (guild_id,)
        ).fetchone()

        if old:
            if old["ends_at"]>now:
                return None

            con.execute(
                """UPDATE boss_games
                SET active=0,
                    result='failed',
                    ended_at=?
                WHERE id=?""",
                (
                    now,
                    old["id"]
                )
            )

        cur=con.execute(
            """INSERT INTO boss_games(
                guild_id,
                channel_id,
                name,
                hp,
                max_hp,
                reward_roses,
                started_at,
                ends_at,
                tell_idx,
                tell_at,
                active,
                testing
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                guild_id,
                channel_id,
                boss_name,
                cfg["hp"],
                cfg["hp"],
                cfg["reward"],
                now,
                now+duration,
                secrets.randbelow(
                    len(tells)
                ),
                now,
                2 if test else 1,
                int(test)
            )
        )

        if automatic:
            con.execute(
                """INSERT INTO boss_spawn(
                    guild_id,
                    last_auto
                ) VALUES(?,?)
                ON CONFLICT(guild_id)
                DO UPDATE SET
                    last_auto=excluded.last_auto""",
                (
                    guild_id,
                    now
                )
            )

        return cur.lastrowid

def message(
    game_id,
    message_id
):
    with connect() as con:
        con.execute(
            """UPDATE boss_games
            SET message_id=?
            WHERE id=?""",
            (
                message_id,
                game_id
            )
        )

def void(game_id):
    with connect() as con:
        con.execute(
            """UPDATE boss_games
            SET active=0,
                result='stopped',
                ended_at=?
            WHERE id=?
            AND active!=0""",
            (
                time.time(),
                game_id
            )
        )

def damage(
    action,
    correct
):
    if action=="strike":
        value=(
            secrets.randbelow(201)
            +450
        )

        return (
            (
                value*3//2
                if correct=="strike"
                else value
            ),
            "hit"
        )

    if action=="guard":
        value=(
            secrets.randbelow(121)
            +180
        )

        return (
            (
                value*5//2
                if correct=="guard"
                else value
            ),
            (
                "blocked"
                if correct=="guard"
                else "guarded"
            )
        )

    chance=(
        0
        if correct=="reckless"
        else (
            50
            if correct=="guard"
            else 25
        )
    )

    if (
        secrets.randbelow(100)
        <chance
    ):
        return 0,"bitten"

    value=(
        secrets.randbelow(401)
        +700
    )

    return (
        (
            value*5//4
            if correct=="reckless"
            else value
        ),
        "reckless"
    )

def bossdamage(
    game,
    action,
    allowed,
    mode
):
    if (
        game["name"]=="xasg"
        and mode=="burning"
    ):
        if action=="reckless":
            if (
                secrets.randbelow(100)
                <25
            ):
                return (
                    0,
                    "risen_fail"
                )

            return (
                secrets.randbelow(501)
                +1000,
                "reckless"
            )

        if action=="strike":
            value=(
                secrets.randbelow(201)
                +500
            )

            return (
                value*5//4,
                "hit"
            )

        return damage(
            action,
            "strike"
        )

    return damage(
        action,
        allowed[0]
    )

def rotate(
    con,
    game,
    now
):
    span=roundtime(
        game
    )

    if (
        now
        <game["tell_at"]+span
    ):
        return game,False

    elapsed=max(
        1,
        int(
            (
                now-game["tell_at"]
            )//span
        )
    )

    tells=config(
        game
    )["tells"]

    nxt=(
        game["tell_idx"]
        +1
        +secrets.randbelow(
            len(tells)-1
        )
    )%len(tells)

    tell_at=(
        game["tell_at"]
        +elapsed*span
    )

    con.execute(
        """UPDATE boss_games
        SET tell_idx=?,
            tell_at=?,
            phase_damage=0
        WHERE id=?""",
        (
            nxt,
            tell_at,
            game["id"]
        )
    )

    game=dict(
        con.execute(
            """SELECT *
            FROM boss_games
            WHERE id=?""",
            (game["id"],)
        ).fetchone()
    )

    return game,True

def accuracy(game):
    total=int(
        game.get(
            "meaningful_actions",
            0
        ) or 0
    )

    correct=int(
        game.get(
            "correct_actions",
            0
        ) or 0
    )

    return correct,total

def unlocked(game):
    if config(
        game
    ).get(
        "fixed_loot",
        False
    ):
        return int(
            game["reward_roses"]
        )

    correct,total=accuracy(
        game
    )

    base=(
        game["reward_roses"]
        //2
    )

    extra=(
        game["reward_roses"]
        -base
    )

    if not total:
        return base

    return (
        base
        +extra*correct//total
    )

def payout(
    con,
    game_id
):
    game=dict(
        con.execute(
            """SELECT *
            FROM boss_games
            WHERE id=?""",
            (game_id,)
        ).fetchone()
    )

    rows=con.execute(
        """SELECT *
        FROM boss_players
        WHERE game_id=?
        AND damage>0
        ORDER BY damage DESC,user_id""",
        (game_id,)
    ).fetchall()

    if not rows:
        con.execute(
            """UPDATE boss_games
            SET active=0,
                result='failed',
                ended_at=?
            WHERE id=?""",
            (
                time.time(),
                game_id
            )
        )
        return

    mvp=rows[0]["user_id"]

    if testing(game):
        con.execute(
            """UPDATE boss_games
            SET active=0,
                result='won',
                mvp_id=?,
                paid_roses=0,
                ended_at=?
            WHERE id=?""",
            (
                mvp,
                time.time(),
                game_id
            )
        )
        return

    paid=unlocked(
        game
    )

    equal=(
        paid*40//100
    )

    scaled=(
        paid-equal
    )

    total=sum(
        item["damage"]
        for item in rows
    )

    shares={
        item["user_id"]:
            equal//len(rows)
            +scaled*item["damage"]//total
        for item in rows
    }

    left=(
        paid
        -sum(shares.values())
    )

    for item in rows:
        if left<=0:
            break

        shares[
            item["user_id"]
        ]+=1

        left-=1

    for item in rows:
        uid=item["user_id"]
        reward=shares[uid]

        con.execute(
            "INSERT OR IGNORE INTO wallets(guild_id,user_id) VALUES(?,?)",
            (game["guild_id"],uid)
        )

        con.execute(
            """UPDATE wallets
            SET roses=roses+?
            WHERE guild_id=?
            AND user_id=?""",
            (
                reward,
                game["guild_id"],
                uid
            )
        )

        con.execute(
            """UPDATE boss_players
            SET reward=?
            WHERE game_id=?
            AND user_id=?""",
            (
                reward,
                game_id,
                uid
            )
        )

        con.execute(
            """INSERT INTO boss_users(
                user_id,
                defeats,
                damage,
                mvps
            ) VALUES(?,1,0,?)
            ON CONFLICT(user_id)
            DO UPDATE SET
                defeats=defeats+1,
                mvps=mvps+excluded.mvps""",
            (
                uid,
                int(uid==mvp)
            )
        )

    con.execute(
        """UPDATE boss_games
        SET active=0,
            result='won',
            mvp_id=?,
            paid_roses=?,
            ended_at=?
        WHERE id=?""",
        (
            mvp,
            paid,
            time.time(),
            game_id
        )
    )

def act(
    guild_id,
    message_id,
    user_id,
    action
):
    now=time.time()

    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        found=con.execute(
            """SELECT *
            FROM boss_games
            WHERE guild_id=?
            AND message_id=?
            AND active!=0
            ORDER BY id DESC
            LIMIT 1""",
            (
                guild_id,
                message_id
            )
        ).fetchone()

        if found is None:
            return {
                "ok":False,
                "reason":"dead"
            }

        game=dict(
            found
        )

        if now>=game["ends_at"]:
            con.execute(
                """UPDATE boss_games
                SET active=0,
                    result='failed',
                    ended_at=?
                WHERE id=?""",
                (
                    now,
                    game["id"]
                )
            )

            return {
                "ok":False,
                "reason":"ended",
                "game":dict(
                    con.execute(
                        """SELECT *
                        FROM boss_games
                        WHERE id=?""",
                        (game["id"],)
                    ).fetchone()
                )
            }

        game,_=rotate(
            con,
            game,
            now
        )

        player=con.execute(
            """SELECT *
            FROM boss_players
            WHERE game_id=?
            AND user_id=?""",
            (
                game["id"],
                user_id
            )
        ).fetchone()

        cd=actioncd(
            game
        )

        if (
            player
            and now<player["last_action"]+cd
        ):
            return {
                "ok":False,
                "reason":"cooldown",
                "ready":
                    player["last_action"]
                    +cd
            }

        quote,scene,allowed,mode=tell(
            game
        )

        base,status=bossdamage(
            game,
            action,
            allowed,
            mode
        )

        pet_bonus=petbuff.bonus(
            user_id,
            "boss",
            base
        )

        dealt=(
            base
            +pet_bonus
        )

        room=max(
            0,
            min(
                PHASE_CAP
                -game["phase_damage"],
                game["hp"]
            )
        )

        meaningful=(
            room>0
        )

        effective=(
            min(
                dealt,
                room
            )
            if meaningful
            else 0
        )

        correct_read=int(
            meaningful
            and action in allowed
        )

        phase_damage=min(
            PHASE_CAP,
            game["phase_damage"]
            +effective
        )

        hp=max(
            0,
            game["hp"]
            -effective
        )

        con.execute(
            """INSERT OR IGNORE INTO boss_players(
                game_id,
                user_id
            ) VALUES(?,?)""",
            (
                game["id"],
                user_id
            )
        )

        con.execute(
            """UPDATE boss_players
            SET damage=damage+?,
                actions=actions+1,
                last_action=?
            WHERE game_id=?
            AND user_id=?""",
            (
                dealt,
                now,
                game["id"],
                user_id
            )
        )

        if not testing(game):
            con.execute(
                """INSERT INTO boss_users(
                    user_id,
                    damage
                ) VALUES(?,?)
                ON CONFLICT(user_id)
                DO UPDATE SET
                    damage=damage+excluded.damage""",
                (
                    user_id,
                    dealt
                )
            )

        con.execute(
            """UPDATE boss_games
            SET hp=?,
                phase_damage=?,
                meaningful_actions=
                    meaningful_actions+?,
                correct_actions=
                    correct_actions+?
            WHERE id=?""",
            (
                hp,
                phase_damage,
                int(meaningful),
                correct_read,
                game["id"]
            )
        )

        if hp<=0:
            payout(
                con,
                game["id"]
            )

        game=dict(
            con.execute(
                """SELECT *
                FROM boss_games
                WHERE id=?""",
                (game["id"],)
            ).fetchone()
        )

        return {
            "ok":True,
            "action":action,
            "damage":dealt,
            "base_damage":base,
            "pet_bonus":pet_bonus,
            "effective":effective,
            "meaningful":meaningful,
            "correct":correct_read,
            "status":status,
            "mode":mode,
            "won":hp<=0,
            "game":game
        }

def stop(guild_id):
    now=time.time()

    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        game=con.execute(
            """SELECT *
            FROM boss_games
            WHERE guild_id=?
            AND active!=0
            ORDER BY id DESC
            LIMIT 1""",
            (guild_id,)
        ).fetchone()

        if game is None:
            return None

        con.execute(
            """UPDATE boss_games
            SET active=0,
                result='stopped',
                ended_at=?
            WHERE id=?""",
            (
                now,
                game["id"]
            )
        )

        return dict(
            con.execute(
                """SELECT *
                FROM boss_games
                WHERE id=?""",
                (game["id"],)
            ).fetchone()
        )

def tick():
    now=time.time()
    expired=[]
    rotated=[]

    with connect() as con:
        rows=con.execute(
            """SELECT *
            FROM boss_games
            WHERE active!=0"""
        ).fetchall()

        for found in rows:
            game=dict(
                found
            )

            if now>=game["ends_at"]:
                con.execute(
                    """UPDATE boss_games
                    SET active=0,
                        result='failed',
                        ended_at=?
                    WHERE id=?""",
                    (
                        now,
                        game["id"]
                    )
                )

                expired.append(
                    game["id"]
                )

                continue

            _,moved=rotate(
                con,
                game,
                now
            )

            if moved:
                rotated.append(
                    game["id"]
                )

    return (
        expired,
        rotated
    )

def bar(game):
    filled=round(
        12
        *game["hp"]
        /game["max_hp"]
    )

    return (
        "█"*filled
        +"░"*(12-filled)
    )

def leaderboard(game):
    ps=players(
        game["id"]
    )

    if not ps:
        return "nobody yet"

    lines=[]

    for index,item in enumerate(
        ps[:15],
        1
    ):
        lines.append(
            f"`{index}.` "
            f"<@{item['user_id']}> "
            f"⊹ **{item['damage']:,}**"
        )

    if len(ps)>15:
        lines.append(
            f"+{len(ps)-15:,} more"
        )

    return "\n".join(
        lines
    )

def decorate(
    embed,
    game
):
    path=art(
        game
    )

    if path.exists():
        embed.set_thumbnail(
            url="attachment://boss.png"
        )

    return embed

def live(game):
    quote,scene,allowed,mode=tell(
        game
    )

    board=leaderboard(
        game
    )

    correct,total=accuracy(
        game
    )

    span=roundtime(
        game
    )

    if (
        game["phase_damage"]
        >=PHASE_CAP
    ):
        move=(
            "*“too slow.”*\n"
            "the opening closes.\n\n"
            f"next opening ⊹ "
            f"<t:{int(game['tell_at']+span)}:R>"
        )

    else:
        move=(
            f"*{quote}*\n"
            f"{scene}\n\n"
            f"opening ⊹ "
            f"**{game['phase_damage']:,} / "
            f"{PHASE_CAP:,} dmg**"
        )

    reads=(
        f"**{correct} / {total} correct**"
        if total
        else "**waiting**"
    )

    if testing(game):
        loot="**disabled in testing**"
    elif game["name"]=="xasg":
        loot=(
            f"**{game['reward_roses']:,} {rosieemoji.ROSE}**"
        )
    else:
        loot=(
            f"**{unlocked(game):,} / {game['reward_roses']:,} {rosieemoji.ROSE}**"
        )

    detail=(
        f"loot ⊹ {loot}"
        if game["name"]=="xasg"
        else (
            f"reads ⊹ {reads}\n"
            f"loot ⊹ {loot}"
        )
    )

    cfg=config(
        game
    )

    intro=(
        cfg["intro"]
        if (
            cfg["intro"]
            and not players(game["id"])
            and not game["phase_damage"]
        )
        else None
    )

    embed=discord.Embed(
        title=cfg["title"],
        description=intro,
        color=discord.Color.dark_red()
    )

    embed.add_field(
        name="health",
        value=(
            f"`{bar(game)}`\n"
            f"**{game['hp']:,} / "
            f"{game['max_hp']:,}**\n"
            f"ends ⊹ "
            f"<t:{int(game['ends_at'])}:R>"
        ),
        inline=True
    )

    embed.add_field(
        name="participants",
        value=board,
        inline=True
    )

    embed.add_field(
        name="move",
        value=(
            f"{move}\n"
            f"{detail}"
        ),
        inline=False
    )

    if testing(game):
        embed.set_footer(
            text="testing mode"
        )

    return decorate(
        embed,
        game
    )

def over(game):
    ps=players(
        game["id"]
    )

    test=testing(
        game
    )

    name=game["name"]

    if game["result"]=="won":
        if name=="xasg":
            ending="**the risen falls.**"

            if test:
                text=(
                    f"{ending}\n\n"
                    "testing kill ⊹ "
                    "**nothing paid or tracked**"
                )

            else:
                paid=int(
                    game.get(
                        "paid_roses",
                        0
                    ) or 0
                )

                text=(
                    f"{ending}\n\nmvp ⊹ <@{game['mvp_id']}>\nloot ⊹ **{paid:,} {rosieemoji.ROSE}**"
                )

        else:
            correct,total=accuracy(
                game
            )

            pct=(
                round(
                    correct*100/total
                )
                if total
                else 0
            )

            ending="**the present stops breathing.**"

            if test:
                text=(
                    f"{ending}\n\n"
                    "testing kill ⊹ "
                    "**nothing paid or tracked**\n"
                    f"reads ⊹ "
                    f"**{correct}/{total} "
                    f"correct • {pct}%**"
                )

            else:
                paid=int(
                    game.get(
                        "paid_roses",
                        0
                    ) or 0
                )

                text=(
                    f"{ending}\n\nmvp ⊹ <@{game['mvp_id']}>\nreads ⊹ **{correct}/{total} correct • {pct}%**\nloot ⊹ **{paid:,} / {game['reward_roses']:,} {rosieemoji.ROSE}**"
                )

    elif game["result"]=="stopped":
        text=(
            (
                "**“mortal.”**\n"
                "xasg descends back through the clouds."
            )
            if name=="xasg"
            else (
                "**“boring.”**\n"
                "the mimic gets put back in storage."
            )
        )

        text+=(
            "\n\nnothing paid out"
        )

    else:
        text=(
            (
                "**“mortal.”**\n"
                "he disappears above the clouds."
            )
            if name=="xasg"
            else (
                "**“thanks for dinner.”**\n"
                "the mimic disappears with the loot."
            )
        )

        text+=(
            f"\n\nhp left ⊹ "
            f"**{game['hp']:,} / "
            f"{game['max_hp']:,}**\n"
            "nothing paid out"
        )

    embed=discord.Embed(
        title=title(
            game
        ),
        description=text,
        color=discord.Color.dark_red()
    )

    if ps:
        lines=[]

        for index,item in enumerate(
            ps[:15],
            1
        ):
            line=(
                f"`{index}.` "
                f"<@{item['user_id']}> "
                f"⊹ **{item['damage']:,}**"
            )

            if (
                not test
                and item["reward"]>0
            ):
                line+=(
                    f" • +{item['reward']:,} {rosieemoji.ROSE}"
                )

            lines.append(
                line
            )

        embed.add_field(
            name="participants",
            value="\n".join(
                lines
            ),
            inline=False
        )

    if test:
        embed.set_footer(
            text="testing mode"
        )

    return decorate(
        embed,
        game
    )

def mimic_response(result):
    action=result["action"]
    effective=result["effective"]

    if result["status"]=="bitten":
        text=(
            "**“MINE.”** "
            "the mimic chews on ur hand "
            "for a second ⊹ **0 dmg**"
        )

    elif not result["meaningful"]:
        text=(
            "**“too slow.”** "
            "the lid is already shut "
            "⊹ **0 hp**"
        )

    elif (
        result["effective"]
        <result["damage"]
    ):
        text=(
            "the lid snaps shut "
            "halfway through "
            f"⊹ **-{effective:,} hp**"
        )

    elif action=="strike":
        if result["correct"]:
            text=(
                "**“OW.”** "
                "the box jerks backward "
                f"⊹ **-{effective:,} hp**\n"
                "✦ good read"
            )
        else:
            text=(
                "you hit the box. "
                "it looks personally offended "
                f"⊹ **-{effective:,} hp**"
            )

    elif action=="guard":
        if result["correct"]:
            text=(
                "**“HEY.”** "
                "it bites down on nothing "
                f"⊹ **-{effective:,} hp**\n"
                "✦ good read"
            )
        else:
            text=(
                "you brace. "
                "the mimic watches you do that "
                f"⊹ **-{effective:,} hp**"
            )

    else:
        if result["correct"]:
            text=(
                "your hand comes back "
                "with all five fingers. nice "
                f"⊹ **-{effective:,} hp**\n"
                "✦ good read"
            )
        else:
            text=(
                "it nearly takes a finger. nearly "
                f"⊹ **-{effective:,} hp**"
            )

    return text

def xasg_response(result):
    action=result["action"]
    effective=result["effective"]

    if result["status"] in (
        "risen_fail",
        "bitten"
    ):
        return (
            "**“it doesn't change the fact "
            "i'm better than you.”** "
            "⊹ **0 dmg**"
        )

    if not result["meaningful"]:
        return (
            "he's already out of reach "
            "⊹ **0 hp**"
        )

    if (
        result["effective"]
        <result["damage"]
    ):
        return (
            "he pulls away before you can finish "
            f"⊹ **-{effective:,} hp**"
        )

    if action=="strike":
        if result["correct"]:
            return (
                "you land a hit on him. "
                "he looks offended "
                f"⊹ **-{effective:,} hp**\n"
                "✦ good read"
            )

        return (
            "your hit clips him "
            f"⊹ **-{effective:,} hp**"
        )

    if action=="guard":
        if result["correct"]:
            return (
                "the sword crashes against your guard "
                f"⊹ **-{effective:,} hp**\n"
                "✦ good read"
            )

        return (
            "you brace. "
            "he wasn't aiming there "
            f"⊹ **-{effective:,} hp**"
        )

    if result["correct"]:
        return (
            "you tear a burning feather free "
            "before he pulls away "
            f"⊹ **-{effective:,} hp**\n"
            "✦ good read"
        )

    return (
        "you reach for him. bad idea "
        f"⊹ **-{effective:,} hp**"
    )

def response(result):
    text=(
        xasg_response(result)
        if result["game"]["name"]=="xasg"
        else mimic_response(result)
    )

    if result["pet_bonus"]:
        text+=(
            f"\n👻 possession ⊹ "
            f"**+{result['pet_bonus']:,} dmg**"
        )

    if result["won"]:
        text+=(
            "\n\n"
            +(
                "**the risen falls.**"
                if result["game"]["name"]=="xasg"
                else "**the present stops breathing.**"
            )
        )

    return text

class BossView(discord.ui.View):
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

    async def go(
        self,
        it,
        action
    ):
        await it.response.defer()

        try:
            result=act(
                it.guild.id,
                it.message.id,
                it.user.id,
                action
            )

            if not result["ok"]:
                if result["reason"]=="cooldown":
                    await it.followup.send(
                        f"not yet ⊹ "
                        f"<t:{int(result['ready'])}:R>",
                        ephemeral=True
                    )
                    return

                game=result.get(
                    "game"
                )

                if game:
                    await it.edit_original_response(
                        embed=over(
                            game
                        ),
                        view=BossView(
                            self.bot,
                            True
                        )
                    )
                else:
                    await it.followup.send(
                        "boss is gone",
                        ephemeral=True
                    )

                return

            game=result["game"]

            await it.edit_original_response(
                embed=(
                    over(game)
                    if result["won"]
                    else live(game)
                ),
                view=(
                    BossView(
                        self.bot,
                        True
                    )
                    if result["won"]
                    else self
                )
            )

            await it.followup.send(
                response(
                    result
                ),
                ephemeral=True
            )

        except discord.HTTPException as error:
            print(
                f"boss discord warning ⊹ {error}"
            )

        except Exception:
            import traceback
            traceback.print_exc()

            try:
                await it.followup.send(
                    "boss error — check logs",
                    ephemeral=True
                )
            except discord.HTTPException:
                pass

    @discord.ui.button(
        emoji="⚔️",
        style=discord.ButtonStyle.danger,
        custom_id="rosie:boss:strike"
    )
    async def strike(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        await self.go(
            it,
            "strike"
        )

    @discord.ui.button(
        emoji="🛡️",
        style=discord.ButtonStyle.secondary,
        custom_id="rosie:boss:guard"
    )
    async def guard(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        await self.go(
            it,
            "guard"
        )

    @discord.ui.button(
        emoji="🫳",
        style=discord.ButtonStyle.success,
        custom_id="rosie:boss:reckless"
    )
    async def reckless(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        await self.go(
            it,
            "reckless"
        )

class Boss(commands.Cog):
    def __init__(
        self,
        bot
    ):
        self.bot=bot
        self.registry_done=False
        self.clock.start()

    async def registry(self):
        if self.registry_done:
            return

        app_id=(
            self.bot.application_id
            or self.bot.user.id
        )

        rows=await self.bot.http.get_global_commands(
            app_id
        )

        row=next(
            (
                item
                for item in rows
                if item.get("name")=="boss"
                and int(item.get("type",1))==1
            ),
            None
        )

        payload={
            "name":"boss",
            "description":"fight whatever rosie woke up",
            "type":1,
            "dm_permission":False,
            "options":[]
        }

        if row is None:
            route=Route(
                "POST",
                "/applications/{application_id}/commands",
                application_id=app_id
            )
        else:
            route=Route(
                "PATCH",
                "/applications/{application_id}/commands/{command_id}",
                application_id=app_id,
                command_id=row["id"]
            )

        await self.bot.http.request(
            route,
            json=payload
        )

        self.registry_done=True

        print(
            "boss command registry ✓"
        )

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            await self.registry()

        except Exception as error:
            print(
                f"boss registry failed ⊹ {error}"
            )

    def cog_unload(self):
        self.clock.cancel()

    async def edit(
        self,
        game,
        disabled=False
    ):
        if (
            game is None
            or game["message_id"] is None
        ):
            return

        channel=self.bot.get_channel(
            game["channel_id"]
        )

        if channel is None:
            return

        try:
            msg=await channel.fetch_message(
                game["message_id"]
            )

            await msg.edit(
                embed=(
                    over(game)
                    if disabled
                    else live(game)
                ),
                view=BossView(
                    self.bot,
                    disabled
                )
            )

        except (
            discord.NotFound,
            discord.Forbidden,
            discord.HTTPException
        ):
            pass

    async def spawn(
        self,
        channel,
        guild_id,
        automatic=False,
        test=False,
        boss_name=None
    ):
        game_id=create(
            guild_id,
            channel.id,
            automatic,
            test,
            boss_name
        )

        if game_id is None:
            return None

        game=get(
            game_id
        )

        try:
            kwargs={}

            path=art(
                game
            )

            if path.exists():
                kwargs["file"]=discord.File(
                    path,
                    filename="boss.png"
                )

            msg=await channel.send(
                embed=live(
                    game
                ),
                view=BossView(
                    self.bot
                ),
                **kwargs
            )

        except (
            discord.Forbidden,
            discord.HTTPException
        ):
            void(
                game_id
            )

            return None

        message(
            game_id,
            msg.id
        )

        if automatic:
            RECENT.pop(
                guild_id,
                None
            )

        return get(
            game_id
        )

    @commands.Cog.listener()
    async def on_message(
        self,
        msg:discord.Message
    ):
        if msg.guild is None:
            return

        channel_id,automatic=spawnconfig(
            msg.guild
        )

        if (
            not automatic
            or channel_id is None
            or msg.channel.id!=channel_id
        ):
            return

        if (
            msg.author.bot
            or msg.webhook_id is not None
        ):
            return

        guild_id=msg.guild.id

        if (
            active(
                guild_id,
                True
            ) is not None
            or not ready(
                guild_id
            )
        ):
            RECENT.pop(
                guild_id,
                None
            )

            return

        count,users=note(
            guild_id,
            msg.author.id
        )

        if (
            count<NEEDED
            or users<USERS
        ):
            return

        await self.spawn(
            msg.channel,
            guild_id,
            True,
            False,
            None
        )

    @tasks.loop(
        seconds=5
    )
    async def clock(self):
        expired,rotated=tick()

        for game_id in expired:
            await self.edit(
                get(
                    game_id
                ),
                True
            )

        for game_id in rotated:
            await self.edit(
                get(
                    game_id
                )
            )

    @clock.before_loop
    async def before(self):
        await self.bot.wait_until_ready()

    @app_commands.command(
        name="boss",
        description="fight whatever rosie woke up"
    )
    @app_commands.guild_only()
    async def boss(
        self,
        it:discord.Interaction
    ):
        game=active(
            it.guild.id,
            True
        )

        if game is None:
            await it.response.send_message(
                "nothing is trying to kill u rn",
                ephemeral=True
            )
            return

        if game["message_id"] is None:
            await it.response.send_message(
                "boss is waking up",
                ephemeral=True
            )
            return

        jump=(
            f"https://discord.com/channels/"
            f"{it.guild.id}/"
            f"{game['channel_id']}/"
            f"{game['message_id']}"
        )

        await it.response.send_message(
            f"{game['name']} is over here ⊹ {jump}",
            ephemeral=True
        )

async def setup(bot):
    petbuff.init()
    guildconfig.init()
    init()

    bot.add_view(
        BossView(bot)
    )

    await bot.add_cog(
        Boss(bot)
    )
