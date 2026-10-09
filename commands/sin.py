import asyncio
import sqlite3
import time
from datetime import date,datetime,timedelta

import discord
from core import database
from core import game as core
from core import sinauto
from discord import app_commands
from discord.http import Route
from discord.ext import commands,tasks
from core import emoji as rosieemoji

TARGET=111.0
MAX_NUMBER=22
DAILY_ROSES=333
WIN_RINGS=3
WIN_ROSES=333
LOCKS={}

def connect():
    con=sqlite3.connect(core.DB)
    con.row_factory=sqlite3.Row
    return con

def init():
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS sin_games(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            testing INTEGER NOT NULL DEFAULT 0,
            target REAL NOT NULL,
            max_number INTEGER NOT NULL,
            started_at REAL NOT NULL,
            current_day TEXT NOT NULL,
            day_no INTEGER NOT NULL DEFAULT 1,
            winner_id INTEGER,
            ended_at REAL
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS sin_choices(
            game_id INTEGER NOT NULL,
            day TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            number INTEGER NOT NULL,
            locked_at REAL NOT NULL,
            PRIMARY KEY(game_id,day,user_id)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS sin_scores(
            game_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            score REAL NOT NULL DEFAULT 0,
            PRIMARY KEY(game_id,user_id)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS sin_users(
            user_id INTEGER PRIMARY KEY,
            sins INTEGER NOT NULL DEFAULT 0
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS sin_autoplay(
            user_id INTEGER PRIMARY KEY,
            game_id INTEGER NOT NULL,
            armed_at REAL NOT NULL
        )""")

        con.execute(
            """DELETE FROM sin_autoplay
            WHERE game_id NOT IN (
                SELECT id
                FROM sin_games
                WHERE active=1
            )"""
        )

        # one live sin globally
        live=con.execute(
            """SELECT id
            FROM sin_games
            WHERE active=1
            AND testing=0
            ORDER BY started_at DESC,id DESC"""
        ).fetchall()

        for row in live[1:]:
            con.execute(
                """UPDATE sin_games
                SET active=0,
                    ended_at=COALESCE(ended_at,?)
                WHERE id=?""",
                (
                    time.time(),
                    row["id"]
                )
            )


def rowdict(row):
    return dict(row) if row else None

def active_game(guild_id):
    with connect() as con:
        row=con.execute("SELECT * FROM sin_games WHERE guild_id=? AND active=1 ORDER BY id DESC LIMIT 1",(guild_id,)).fetchone()
    return rowdict(row)

def active_global_game():
    with connect() as con:
        row=con.execute(
            """SELECT *
            FROM sin_games
            WHERE active=1
            AND testing=0
            ORDER BY started_at DESC,id DESC
            LIMIT 1"""
        ).fetchone()

    return rowdict(row)

def active_real_games():
    game=active_global_game()

    return (
        [game]
        if game
        else []
    )

def get_game(game_id):
    with connect() as con:
        row=con.execute("SELECT * FROM sin_games WHERE id=?",(game_id,)).fetchone()
    return rowdict(row)

def create_game(guild_id,channel_id,target=None):
    now=time.time()
    target=float(
        target
        if target is not None
        else TARGET
    )
    today=core.day().isoformat()

    with connect() as con:
        con.execute(
            """DELETE FROM sin_autoplay
            WHERE game_id IN (
                SELECT id
                FROM sin_games
                WHERE active=1
                AND testing=0
            )"""
        )

        con.execute(
            """UPDATE sin_games
            SET active=0,
                ended_at=COALESCE(ended_at,?)
            WHERE active=1
            AND testing=0""",
            (
                now,
            )
        )

        cur=con.execute(
            """INSERT INTO sin_games(
                guild_id,
                channel_id,
                testing,
                target,
                max_number,
                started_at,
                current_day
            ) VALUES(?,?,?,?,?,?,?)""",
            (
                guild_id,
                channel_id,
                0,
                target,
                MAX_NUMBER,
                now,
                today
            )
        )

        return cur.lastrowid

def stop_game(game_id):
    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        con.execute(
            """UPDATE sin_games
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
            """DELETE FROM sin_autoplay
            WHERE game_id=?""",
            (
                game_id,
            )
        )

def lock_choice(game_id,day,user_id,number):
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        row=con.execute("SELECT number FROM sin_choices WHERE game_id=? AND day=? AND user_id=?",(game_id,day,user_id)).fetchone()
        if row:
            return False,row["number"]
        con.execute("INSERT INTO sin_choices(game_id,day,user_id,number,locked_at) VALUES(?,?,?,?,?)",(game_id,day,user_id,number,time.time()))
    return True,number

def standings(game_id):
    with connect() as con:
        rows=con.execute("SELECT user_id,score FROM sin_scores WHERE game_id=? ORDER BY score DESC,user_id ASC",(game_id,)).fetchall()
    return [dict(row) for row in rows]

def auto_rows(game_id=None):
    with connect() as con:
        if game_id is None:
            rows=con.execute(
                """SELECT *
                FROM sin_autoplay
                ORDER BY armed_at,user_id"""
            ).fetchall()
        else:
            rows=con.execute(
                """SELECT *
                FROM sin_autoplay
                WHERE game_id=?
                ORDER BY armed_at,user_id""",
                (
                    game_id,
                )
            ).fetchall()

    return [
        dict(row)
        for row in rows
    ]

def auto_team(game_id):
    return tuple(
        int(row["user_id"])
        for row in auto_rows(
            game_id
        )[:2]
    )

def auto_toggle(game_id,user_id):
    game_id=int(
        game_id
    )

    user_id=int(
        user_id
    )

    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        game=con.execute(
            """SELECT id
            FROM sin_games
            WHERE id=?
            AND active=1""",
            (
                game_id,
            )
        ).fetchone()

        if game is None:
            return {
                "ok":False,
                "reason":"dead",
                "armed":False,
                "team":()
            }

        current=con.execute(
            """SELECT game_id
            FROM sin_autoplay
            WHERE user_id=?""",
            (
                user_id,
            )
        ).fetchone()

        if (
            current is not None
            and int(
                current[
                    "game_id"
                ]
            )==game_id
        ):
            con.execute(
                """DELETE FROM sin_autoplay
                WHERE user_id=?""",
                (
                    user_id,
                )
            )

            rows=con.execute(
                """SELECT user_id
                FROM sin_autoplay
                WHERE game_id=?
                ORDER BY armed_at,user_id""",
                (
                    game_id,
                )
            ).fetchall()

            return {
                "ok":True,
                "reason":"disarmed",
                "armed":False,
                "team":tuple(
                    int(row["user_id"])
                    for row in rows
                )
            }

        rows=con.execute(
            """SELECT user_id
            FROM sin_autoplay
            WHERE game_id=?
            ORDER BY armed_at,user_id""",
            (
                game_id,
            )
        ).fetchall()

        if len(rows)>=2:
            return {
                "ok":False,
                "reason":"full",
                "armed":False,
                "team":tuple(
                    int(row["user_id"])
                    for row in rows
                )
            }

        if current is not None:
            con.execute(
                """DELETE FROM sin_autoplay
                WHERE user_id=?""",
                (
                    user_id,
                )
            )

        con.execute(
            """INSERT INTO sin_autoplay(
                user_id,game_id,armed_at
            ) VALUES(?,?,?)""",
            (
                user_id,
                game_id,
                time.time()
            )
        )

        rows=con.execute(
            """SELECT user_id
            FROM sin_autoplay
            WHERE game_id=?
            ORDER BY armed_at,user_id""",
            (
                game_id,
            )
        ).fetchall()

    return {
        "ok":True,
        "reason":"armed",
        "armed":True,
        "team":tuple(
            int(row["user_id"])
            for row in rows
        )
    }

def auto_fire(day_key):
    day=date.fromisoformat(
        day_key
    )

    return datetime(
        day.year,
        day.month,
        day.day,
        23,
        59,
        55,
        tzinfo=core.ET
    ).timestamp()

def auto_plan(game,team,con=None):
    if con is None:
        with connect() as current:
            return auto_plan(
                game,
                team,
                current
            )

    picks={
        int(row["user_id"]):
            int(row["number"])
        for row in con.execute(
            """SELECT user_id,number
            FROM sin_choices
            WHERE game_id=?
            AND day=?""",
            (
                game["id"],
                game["current_day"]
            )
        ).fetchall()
    }

    scores={
        int(row["user_id"]):
            float(row["score"])
        for row in con.execute(
            """SELECT user_id,score
            FROM sin_scores
            WHERE game_id=?""",
            (
                game["id"],
            )
        ).fetchall()
    }

    return sinauto.plan(
        game["max_number"],
        game["target"],
        picks,
        scores,
        team
    )

def auto_lock(game_id):
    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        row=con.execute(
            """SELECT *
            FROM sin_games
            WHERE id=?
            AND active=1""",
            (
                game_id,
            )
        ).fetchone()

        if row is None:
            return {
                "ok":False,
                "reason":"dead"
            }

        game=dict(
            row
        )

        rows=con.execute(
            """SELECT user_id
            FROM sin_autoplay
            WHERE game_id=?
            ORDER BY armed_at,user_id
            LIMIT 2""",
            (
                game_id,
            )
        ).fetchall()

        team=tuple(
            int(row["user_id"])
            for row in rows
        )

        if not team:
            return {
                "ok":False,
                "reason":"unarmed"
            }

        plan=auto_plan(
            game,
            team,
            con
        )

        locked={}

        for user_id,number in plan[
            "best"
        ][
            "actions"
        ].items():
            cur=con.execute(
                """INSERT OR IGNORE INTO sin_choices(
                    game_id,
                    day,
                    user_id,
                    number,
                    locked_at
                ) VALUES(?,?,?,?,?)""",
                (
                    game_id,
                    game[
                        "current_day"
                    ],
                    user_id,
                    number,
                    time.time()
                )
            )

            if cur.rowcount:
                locked[
                    user_id
                ]=number

    return {
        "ok":True,
        "game":game,
        "team":team,
        "plan":plan,
        "locked":locked
    }


def test_embed(game):
    with connect() as con:
        rows=con.execute(
            """SELECT user_id,number
            FROM sin_choices
            WHERE game_id=?
            AND day=?
            ORDER BY number DESC,user_id""",
            (
                game["id"],
                game["current_day"]
            )
        ).fetchall()

    groups={
        number:[]
        for number in range(
            1,
            int(
                game[
                    "max_number"
                ]
            )+1
        )
    }

    for row in rows:
        groups[
            int(
                row[
                    "number"
                ]
            )
        ].append(
            int(
                row[
                    "user_id"
                ]
            )
        )

    hidden=[]

    for number in range(
        int(
            game[
                "max_number"
            ]
        ),
        0,
        -1
    ):
        users=groups[
            number
        ]

        if users:
            shown=users[:4]

            people=" ".join(
                f"<@{user_id}>"
                for user_id in shown
            )

            if len(users)>4:
                people+=(
                    f" +{len(users)-4}"
                )

            value=(
                number
                /len(users)
            )

            hidden.append(
                f"**{number}** ⊹ "
                f"{people} ⊹ "
                f"{value:.3f}"
            )

        else:
            hidden.append(
                f"**{number}** ⊹ —"
            )

    team=auto_team(
        game["id"]
    )

    parts=[
        "**hidden picks**",
        *hidden,
        "",
        "**autoplay**"
    ]

    if not team:
        parts.append(
            "unarmed"
        )

    else:
        plan=auto_plan(
            game,
            team
        )

        best=plan[
            "best"
        ]

        parts.append(
            f"mode ⊹ **{plan['mode']}** ⊹ "
            +" + ".join(
                f"<@{user_id}>"
                for user_id in team
            )
        )

        parts.append(
            f"fires ⊹ "
            f"<t:{int(auto_fire(game['current_day']))}:T>"
        )

        if plan[
            "mode"
        ]=="solo":
            user_id=team[
                0
            ]

            number=best[
                "choices"
            ][
                user_id
            ]

            parts.extend((
                (
                    f"recommended now ⊹ "
                    f"<@{user_id}> "
                    f"**{number}**"
                ),
                (
                    f"gain ⊹ "
                    f"**{best['gain']:.3f}** "
                    f"• rank ⊹ "
                    f"**#{best['ranks'].get(user_id,1)}** "
                    f"• gap ⊹ "
                    f"**{best['gap']:+.3f}**"
                ),
                (
                    f"denied ⊹ "
                    f"**{best['denied']:.3f}** "
                    f"• pressure ⊹ "
                    f"**{best['race_pressure']:.3f}**"
                ),
                (
                    f"reason ⊹ "
                    f"**{plan['reason']}**"
                ),
                "",
                "**top candidates**"
            ))

            for index,item in enumerate(
                plan[
                    "top"
                ],
                1
            ):
                number=item[
                    "choices"
                ][
                    user_id
                ]

                parts.append(
                    f"{index}. "
                    f"**{number}** ⊹ "
                    f"+{item['gain']:.3f} "
                    f"• #{item['ranks'].get(user_id,1)} "
                    f"• deny {item['denied']:.3f} "
                    f"• pressure {item['race_pressure']:.3f}"
                )

        else:
            captain=plan[
                "captain"
            ]

            wing=plan[
                "wing"
            ]

            parts.extend((
                (
                    f"captain ⊹ "
                    f"<@{captain}> "
                    f"**{best['choices'][captain]}**"
                ),
                (
                    f"wing ⊹ "
                    f"<@{wing}> "
                    f"**{best['choices'][wing]}**"
                ),
                (
                    f"ranks ⊹ "
                    f"**#{best['ranks'].get(captain,1)} / "
                    f"#{best['ranks'].get(wing,1)}** "
                    f"• team gain ⊹ "
                    f"**{best['team_gain']:.3f}**"
                ),
                (
                    f"denied ⊹ "
                    f"**{best['denied']:.3f}** "
                    f"• pressure ⊹ "
                    f"**{best['race_pressure']:.3f}** "
                    f"• captain gap ⊹ "
                    f"**{best['gap']:+.3f}**"
                ),
                (
                    f"reason ⊹ "
                    f"**{plan['reason']}**"
                ),
                "",
                "**top pairs**"
            ))

            for index,item in enumerate(
                plan[
                    "top"
                ],
                1
            ):
                parts.append(
                    f"{index}. "
                    f"**{item['choices'][captain]} + "
                    f"{item['choices'][wing]}** ⊹ "
                    f"#{item['ranks'].get(captain,1)}/"
                    f"#{item['ranks'].get(wing,1)} "
                    f"• gain {item['team_gain']:.3f} "
                    f"• deny {item['denied']:.3f} "
                    f"• pressure {item['race_pressure']:.3f}"
                )

    return discord.Embed(
        title=(
            f"♦️ sin test - "
            f"day {game['day_no']}"
        ),
        description="\n".join(
            parts
        )[:4090],
        color=discord.Color.dark_red()
    )

def midnight_after(day_key):
    d=date.fromisoformat(day_key)+timedelta(days=1)
    return int(datetime(d.year,d.month,d.day,tzinfo=core.ET).timestamp())

def resolve_day(game):
    day_key=game["current_day"]

    with connect() as con:
        con.execute(
            "ATTACH DATABASE ? AS econ",
            (str(database.FILE),)
        )
        con.execute("BEGIN IMMEDIATE")

        rows=con.execute(
            """SELECT user_id,number
            FROM sin_choices
            WHERE game_id=? AND day=?
            ORDER BY user_id""",
            (game["id"],day_key)
        ).fetchall()

        counts={}
        for row in rows:
            counts[row["number"]]=counts.get(row["number"],0)+1

        gains=[]

        for row in rows:
            gain=row["number"]/counts[row["number"]]
            gains.append({
                "user_id":row["user_id"],
                "number":row["number"],
                "gain":gain
            })
            con.execute(
                """INSERT INTO sin_scores(game_id,user_id,score)
                VALUES(?,?,?)
                ON CONFLICT(game_id,user_id)
                DO UPDATE SET score=score+excluded.score""",
                (game["id"],row["user_id"],gain)
            )

        score_rows=[
            dict(row)
            for row in con.execute(
                """SELECT user_id,score
                FROM sin_scores
                WHERE game_id=?
                ORDER BY score DESC,user_id ASC""",
                (game["id"],)
            ).fetchall()
        ]

        winner=None
        if score_rows and score_rows[0]["score"]>=game["target"]:
            if len(score_rows)==1 or score_rows[0]["score"]>score_rows[1]["score"]+1e-9:
                winner=score_rows[0]

        if winner:
            con.execute(
                """UPDATE sin_games
                SET active=0,winner_id=?,ended_at=?
                WHERE id=?""",
                (winner["user_id"],time.time(),game["id"])
            )

            con.execute(
                """DELETE FROM sin_autoplay
                WHERE game_id=?""",
                (
                    game["id"],
                )
            )
        else:
            next_day=(date.fromisoformat(day_key)+timedelta(days=1)).isoformat()
            con.execute(
                """UPDATE sin_games
                SET current_day=?,day_no=day_no+1
                WHERE id=?""",
                (next_day,game["id"])
            )

        daily_awards={}

        if gains and not game["testing"]:
            best=max(row["gain"] for row in gains)
            leaders=sorted(
                row["user_id"]
                for row in gains
                if abs(row["gain"]-best)<1e-9
            )
            base=DAILY_ROSES//len(leaders)
            extra=DAILY_ROSES%len(leaders)

            for i,user_id in enumerate(leaders):
                amount=base+(1 if i<extra else 0)
                if not amount:
                    continue

                con.execute(
                    "INSERT OR IGNORE INTO users(user_id) VALUES(?)",
                    (user_id,)
                )
                con.execute(
                    "INSERT OR IGNORE INTO econ.wallets(guild_id,user_id) VALUES(?,?)",
                    (game["guild_id"],user_id)
                )
                con.execute(
                    "UPDATE econ.wallets SET roses=roses+? WHERE guild_id=? AND user_id=?",
                    (amount,game["guild_id"],user_id)
                )
                daily_awards[user_id]=amount

        if winner and not game["testing"]:
            user_id=winner["user_id"]
            con.execute(
                "INSERT OR IGNORE INTO users(user_id) VALUES(?)",
                (user_id,)
            )
            con.execute(
                "INSERT OR IGNORE INTO econ.wallets(guild_id,user_id) VALUES(?,?)",
                (game["guild_id"],user_id)
            )
            con.execute(
                """UPDATE econ.wallets
                SET rings=rings+?,roses=roses+?
                WHERE guild_id=? AND user_id=?""",
                (WIN_RINGS,WIN_ROSES,game["guild_id"],user_id)
            )
            con.execute(
                "INSERT OR IGNORE INTO sin_users(user_id) VALUES(?)",
                (user_id,)
            )
            con.execute(
                "UPDATE sin_users SET sins=sins+1 WHERE user_id=?",
                (user_id,)
            )

        fresh=dict(
            con.execute(
                "SELECT * FROM sin_games WHERE id=?",
                (game["id"],)
            ).fetchone()
        )

    return {
        "day":day_key,
        "day_no":game["day_no"],
        "counts":counts,
        "gains":gains,
        "daily_awards":daily_awards,
        "standings":score_rows,
        "winner":winner,
        "game":fresh
    }

def rules_embed(game=None):
    target=game["target"] if game else TARGET
    max_number=game["max_number"] if game else MAX_NUMBER
    testing=bool(game and game["testing"])
    text=f'pick one number from **1 - {max_number}**. lock it anywhere with `/sin number: #`.\n\nat midnight, your number is divided by everyone who chose the same thing. e.g. {max_number} alone ⊹ {max_number} points, {max_number} with 2 people ⊹ {max_number / 2:g} points each.\n\ndaily high score ⊹ **333 roses {rosieemoji.ROSE}** split between ties.\n\nbe greedy.\n\nfirst leader to **{target:,.0f}** becomes a **Sinner**.\n\n**reward**\n⊹ {WIN_RINGS} rings 💍 + {WIN_ROSES:,} roses {rosieemoji.ROSE}'
    if game and not testing:
        text+=f"\n\n**day {game['day_no']}**\ncloses ⊹ <t:{midnight_after(game['current_day'])}:R>"
    embed=discord.Embed(title="♦️ sin",description=text,color=discord.Color.dark_red())
    if testing:
        embed.set_footer(text="testing mode")
    return embed

def day_embed(game):
    with connect() as con:
        stats=con.execute(
            """SELECT
                COUNT(DISTINCT user_id) AS participants,
                COUNT(*) AS picks
            FROM sin_choices
            WHERE game_id=?""",
            (
                game["id"],
            )
        ).fetchone()

    rows=standings(
        game["id"]
    )

    board=(
        "\n".join(
            f"**{i}.** <@{row['user_id']}> ⊹ {row['score']:.3f}"
            for i,row in enumerate(
                rows[:5],
                1
            )
        )
        if rows
        else "nobody"
    )

    embed=discord.Embed(
        title=f"♦️ sin - day {game['day_no']}",
        description=(
            f"participants ⊹ **{stats['participants']:,}**\n"
            f"season picks ⊹ **{stats['picks']:,}**\n\n"
            f"**overall**\n"
            f"{board}\n\n"
            f"pick **1 - {game['max_number']}**\n"
            f"closes ⊹ <t:{midnight_after(game['current_day'])}:R>"
        ),
        color=discord.Color.dark_red()
    )

    if game["testing"]:
        embed.set_footer(
            text="testing mode"
        )

    return embed


def result_embed(game,result):
    if result["counts"]:
        groups="\n".join(f"{number} ⊹ {count} picked ⊹ {number/count:.3f}" for number,count in sorted(result["counts"].items(),reverse=True))
    else:
        groups="nobody picked anything"
    nightly=sorted(result["gains"],key=lambda row:(-row["gain"],row["user_id"]))
    if nightly:
        lines=[]
        for i,row in enumerate(nightly[:5],1):
            bonus=result["daily_awards"].get(row["user_id"])
            line=f"**{i}.** <@{row['user_id']}> ⊹ {row['gain']:.3f}"
            if bonus:
                line+=f'\n⊹ {bonus:,} roses {rosieemoji.ROSE}'
            lines.append(line)
        tonight="\n".join(lines)
    else:
        tonight="nobody"
    overall=result["standings"]
    if overall:
        board="\n".join(f"**{i}.** <@{row['user_id']}> ⊹ {row['score']:.3f}" for i,row in enumerate(overall[:5],1))
    else:
        board="nobody"
    embed=discord.Embed(title=f"♦️ sin - day {result['day_no']}",description=f"**results**\n{groups}\n\n**tonight**\n{tonight}\n\n**overall**\n{board}",color=discord.Color.dark_red())
    if game["testing"]:
        embed.set_footer(text="testing mode")
    return embed

def winner_embed(game,result):
    winner=result["winner"]
    text=f"<@{winner['user_id']}> hit **{winner['score']:.3f}** and becomes a **Sinner**"
    if not game["testing"]:
        text+=f'\n\n⊹ {WIN_RINGS} rings 💍 ⊹ {WIN_ROSES:,} roses {rosieemoji.ROSE}'
    embed=discord.Embed(title="♦️ sin",description=text,color=discord.Color.dark_red())
    if game["testing"]:
        embed.set_footer(text="testing mode")
    return embed

class SinView(discord.ui.View):
    def __init__(self,bot):
        super().__init__(timeout=None)
        self.bot=bot

    @discord.ui.button(emoji="❓",style=discord.ButtonStyle.secondary,custom_id="rosie:sin:rules")
    async def rules(self,it:discord.Interaction,button:discord.ui.Button):
        game=active_game(it.guild.id)
        await it.response.send_message(embed=rules_embed(game),ephemeral=True)

class Sin(commands.Cog):
    def __init__(self,bot):
        self.bot=bot
        self.registry_done=False
        self.auto_seen=set()
        self.resolver.start()
        self.auto_clock.start()

    def cog_unload(self):
        self.resolver.cancel()
        self.auto_clock.cancel()

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
                if item.get("name")=="sin"
                and int(item.get("type",1))==1
            ),
            None
        )

        payload={
            "name":"sin",
            "description":"be greedy",
            "type":1,
            "dm_permission":False,
            "options":[
                {
                    "type":4,
                    "name":"number",
                    "description":f"pick 1 - {MAX_NUMBER}",
                    "required":False
                }
            ]
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
            "sin command registry ✓"
        )

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            await self.registry()

        except Exception as error:
            print(
                f"sin registry failed ⊹ {error}"
            )


    async def catch_up(self,guild_id):
        lock=LOCKS.setdefault(guild_id,asyncio.Lock())
        async with lock:
            game=active_game(guild_id)
            if game is None or game["testing"]:
                return
            today=core.day().isoformat()
            while game and game["active"] and game["current_day"]<today:
                result=resolve_day(game)
                try:
                    channel=self.bot.get_channel(game["channel_id"]) or await self.bot.fetch_channel(game["channel_id"])
                    await channel.send(embed=result_embed(game,result))
                    if result["winner"]:
                        await channel.send(embed=winner_embed(game,result))
                        return
                    game=result["game"]
                except discord.HTTPException:
                    pass
                game=active_game(guild_id)

    @tasks.loop(seconds=30)
    async def resolver(self):
        for game in active_real_games():
            try:
                await self.catch_up(game["guild_id"])
            except Exception as e:
                print(f"sin resolver: {e}")

    @tasks.loop(seconds=1)
    async def auto_clock(self):
        if not self.bot.is_ready():
            return

        game=active_global_game()

        if game is None:
            return

        team=auto_team(
            game["id"]
        )

        if not team:
            return

        if (
            game[
                "current_day"
            ]
            !=core.day().isoformat()
        ):
            return

        if time.time()<auto_fire(
            game[
                "current_day"
            ]
        ):
            return

        key=(
            game["id"],
            game["current_day"],
            team
        )

        if key in self.auto_seen:
            return

        lock=LOCKS.setdefault(
            game["guild_id"],
            asyncio.Lock()
        )

        async with lock:
            fresh=get_game(
                game["id"]
            )

            if (
                fresh is None
                or not fresh[
                    "active"
                ]
                or fresh[
                    "current_day"
                ]!=game[
                    "current_day"
                ]
            ):
                return

            if auto_team(
                game["id"]
            )!=team:
                return

            result=auto_lock(
                game["id"]
            )

        if not result[
            "ok"
        ]:
            return

        self.auto_seen.add(
            key
        )

        if not result[
            "locked"
        ]:
            return

        plan=result[
            "plan"
        ]

        best=plan[
            "best"
        ]

        if plan[
            "mode"
        ]=="solo":
            user_id=team[
                0
            ]

            text=(
                "sin autoplay ♦️\n"
                f"locked ⊹ "
                f"**{best['choices'][user_id]}**\n"
                f"reason ⊹ "
                f"{plan['reason']}"
            )

        else:
            captain=plan[
                "captain"
            ]

            wing=plan[
                "wing"
            ]

            text=(
                "sin twin autoplay ♦️\n"
                f"<@{captain}> ⊹ "
                f"**{best['choices'][captain]}**\n"
                f"<@{wing}> ⊹ "
                f"**{best['choices'][wing]}**\n"
                f"reason ⊹ "
                f"{plan['reason']}"
            )

        for user_id in team:
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

            if user is None:
                continue

            try:
                await user.send(
                    text
                )
            except discord.HTTPException:
                pass

        print(
            f"sin autoplay ⊹ "
            f"game {game['id']} ⊹ "
            f"{plan['mode']} ⊹ "
            +", ".join(
                f"{user_id}:"
                f"{best['choices'][user_id]}"
                for user_id in team
            )
        )

    @resolver.before_loop
    async def before_resolver(self):
        await self.bot.wait_until_ready()

    @app_commands.command(
        name="sin",
        description="be greedy"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        number='number'
    )
    async def sin(
        self,
        it:discord.Interaction,
        number:int|None=None
    ):
        if number is not None:
            await self.catch_up(
                it.guild.id
            )

            game=active_game(
                it.guild.id
            )

            if game is None:
                await it.response.send_message(
                    "no sin game rn",
                    ephemeral=True
                )
                return

            if (
                number<1
                or number>game["max_number"]
            ):
                await it.response.send_message(
                    f"pick 1 - {game['max_number']}",
                    ephemeral=True
                )
                return

            core.touch(
                it.user.id
            )

            locked,value=lock_choice(
                game["id"],
                game["current_day"],
                it.user.id,
                number
            )

            if not locked:
                await it.response.send_message(
                    f"already locked ⊹ {value}",
                    ephemeral=True
                )
                return

            await it.response.send_message(
                f"locked ⊹ {value}",
                ephemeral=True
            )
            return

        await self.catch_up(
            it.guild.id
        )

        game=active_game(
            it.guild.id
        )

        await it.response.send_message(
            embed=rules_embed(
                game
            )
        )

async def setup(bot):
    init()
    bot.add_view(SinView(bot))
    await bot.add_cog(Sin(bot))
