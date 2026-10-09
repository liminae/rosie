
import asyncio
import json
import re
import secrets
import sqlite3
import time
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo

import discord
from core import database
from core import game
from core import guildconfig
from core import legacyconfig
from discord import app_commands
from discord.ext import commands,tasks
from discord.http import Route
from core import emoji as rosieemoji

ET=ZoneInfo("America/New_York")
COST=500
BASE=25000
ADD=200
LIMIT=10
DAYS=(0,2,5)
HOUR=21
PING_EVERY=25

def connect():
    con=sqlite3.connect(database.FILE,timeout=15)
    con.row_factory=sqlite3.Row
    return con

def today():
    return datetime.now(ET)

def pick():
    return (
        sorted(
            secrets.SystemRandom().sample(
                range(1,11),
                3
            )
        ),
        secrets.randbelow(5)+1
    )

def nextdraw(stamp=None):
    now=(
        datetime.fromtimestamp(stamp,ET)
        if stamp is not None
        else today()
    )

    for offset in range(8):
        day=(now+timedelta(days=offset)).date()

        if day.weekday() not in DAYS:
            continue

        target=datetime(
            day.year,
            day.month,
            day.day,
            HOUR,
            tzinfo=ET
        )

        if target>now:
            return target.timestamp()

    raise RuntimeError("draw schedule failed")

def init():
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS draw_rounds(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            draws_at REAL NOT NULL,
            jackpot INTEGER NOT NULL,
            tickets INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'open',
            numbers TEXT,
            thorn INTEGER,
            created_at REAL NOT NULL,
            resolved_at REAL
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS draw_tickets(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            round_id INTEGER NOT NULL,
            guild_id INTEGER,
            user_id INTEGER NOT NULL,
            numbers TEXT NOT NULL,
            thorn INTEGER NOT NULL,
            cost INTEGER NOT NULL,
            payout INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS draw_channels(
            round_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            UNIQUE(round_id,guild_id)
        )""")
        ticketcols={row[1] for row in con.execute("PRAGMA table_info(draw_tickets)")}
        if "guild_id" not in ticketcols:
            con.execute("ALTER TABLE draw_tickets ADD COLUMN guild_id INTEGER")
        con.execute(
            "CREATE INDEX IF NOT EXISTS draw_ticket_round "
            "ON draw_tickets(round_id,user_id)"
        )
        ensure(con)

def migrateguild(guild_id):
    with connect() as con:
        con.execute("UPDATE draw_tickets SET guild_id=? WHERE guild_id IS NULL",(guild_id,))

def ensure(con=None,pot=BASE):
    own=con is None
    db=con or connect()

    try:
        found=db.execute(
            """SELECT *
            FROM draw_rounds
            WHERE status='open'
            ORDER BY id DESC LIMIT 1"""
        ).fetchone()

        if found:
            data=dict(found)

            if (
                not data.get("numbers")
                or not data.get("thorn")
            ):
                numbers,thorn=pick()

                db.execute(
                    """UPDATE draw_rounds
                    SET numbers=?,thorn=?
                    WHERE id=?""",
                    (
                        json.dumps(numbers),
                        thorn,
                        data["id"]
                    )
                )

                found=db.execute(
                    "SELECT * FROM draw_rounds WHERE id=?",
                    (data["id"],)
                ).fetchone()

            if own:
                db.commit()

            return dict(found)

        numbers,thorn=pick()
        now=time.time()

        cur=db.execute(
            """INSERT INTO draw_rounds(
                draws_at,
                jackpot,
                numbers,
                thorn,
                created_at
            ) VALUES(?,?,?,?,?)""",
            (
                nextdraw(now),
                pot,
                json.dumps(numbers),
                thorn,
                now
            )
        )

        found=db.execute(
            "SELECT * FROM draw_rounds WHERE id=?",
            (cur.lastrowid,)
        ).fetchone()

        if own:
            db.commit()

        return dict(found)

    finally:
        if own:
            db.close()

def current():
    with connect() as con:
        return ensure(con)

def last():
    with connect() as con:
        found=con.execute(
            """SELECT *
            FROM draw_rounds
            WHERE status='resolved'
            ORDER BY id DESC LIMIT 1"""
        ).fetchone()

    return dict(found) if found else None

def watch(drawid,guildid,channelid):
    if not guildid or not channelid:
        return

    with connect() as con:
        con.execute(
            """INSERT INTO draw_channels(
                round_id,
                guild_id,
                channel_id
            ) VALUES(?,?,?)
            ON CONFLICT(round_id,guild_id)
            DO UPDATE
            SET channel_id=excluded.channel_id""",
            (
                drawid,
                guildid,
                channelid
            )
        )

def counts(uid,drawid):
    with connect() as con:
        mine=con.execute(
            """SELECT COUNT(*)
            FROM draw_tickets
            WHERE round_id=? AND user_id=?""",
            (
                drawid,
                uid
            )
        ).fetchone()[0]

        total=con.execute(
            """SELECT COUNT(*)
            FROM draw_tickets
            WHERE round_id=?""",
            (drawid,)
        ).fetchone()[0]

    return mine,total

def tickets(uid,drawid):
    with connect() as con:
        rows=con.execute(
            """SELECT *
            FROM draw_tickets
            WHERE round_id=? AND user_id=?
            ORDER BY id""",
            (
                drawid,
                uid
            )
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]

def alltickets(drawid):
    with connect() as con:
        rows=con.execute(
            """SELECT *
            FROM draw_tickets
            WHERE round_id=?
            ORDER BY id""",
            (drawid,)
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]

def combo(numbers,thorn):
    return (
        " • ".join(
            str(n)
            for n in sorted(numbers)
        )
        +f" + 🥀 {thorn}"
    )

def parse(text):
    numbers=[
        int(value)
        for value in re.findall(
            r"\d+",
            text
        )
    ]

    if (
        len(numbers)!=3
        or len(set(numbers))!=3
        or any(
            n<1 or n>10
            for n in numbers
        )
    ):
        return None

    return sorted(numbers)

def buy(
    uid,
    numbers=None,
    thorn=None,
    guildid=None,
    channelid=None
):
    if numbers is None:
        numbers=sorted(
            secrets.SystemRandom().sample(
                range(1,11),
                3
            )
        )

    if thorn is None:
        thorn=secrets.randbelow(5)+1

    if (
        len(numbers)!=3
        or len(set(numbers))!=3
        or any(
            n<1 or n>10
            for n in numbers
        )
        or thorn<1
        or thorn>5
    ):
        return {
            "ok":False,
            "reason":"numbers"
        }

    with connect() as con:
        con.execute("BEGIN IMMEDIATE")

        draw=ensure(con)

        if draw["draws_at"]<=time.time():
            return {
                "ok":False,
                "reason":"drawing"
            }

        count=con.execute(
            """SELECT COUNT(*)
            FROM draw_tickets
            WHERE round_id=? AND user_id=?""",
            (
                draw["id"],
                uid
            )
        ).fetchone()[0]

        if count>=LIMIT:
            return {
                "ok":False,
                "reason":"limit"
            }

        duplicate=con.execute(
            """SELECT 1
            FROM draw_tickets
            WHERE round_id=?
            AND user_id=?
            AND numbers=?
            AND thorn=?
            LIMIT 1""",
            (
                draw["id"],
                uid,
                json.dumps(numbers),
                thorn
            )
        ).fetchone()

        if duplicate:
            return {
                "ok":False,
                "reason":"duplicate"
            }

        if guildid is None:
            return {
                "ok":False,
                "reason":"broke",
                "need":COST
            }

        con.execute(
            "INSERT OR IGNORE INTO wallets(guild_id,user_id) VALUES(?,?)",
            (guildid,uid)
        )

        roses=con.execute(
            "SELECT roses FROM wallets WHERE guild_id=? AND user_id=?",
            (guildid,uid)
        ).fetchone()[0]

        if roses<COST:
            return {
                "ok":False,
                "reason":"broke",
                "need":COST-roses
            }

        con.execute(
            "UPDATE wallets SET roses=roses-? WHERE guild_id=? AND user_id=?",
            (
                COST,
                guildid,
                uid
            )
        )

        cur=con.execute(
            """INSERT INTO draw_tickets(
                round_id,
                guild_id,
                user_id,
                numbers,
                thorn,
                cost,
                created_at
            ) VALUES(?,?,?,?,?,?,?)""",
            (
                draw["id"],
                guildid,
                uid,
                json.dumps(numbers),
                thorn,
                COST,
                time.time()
            )
        )

        con.execute(
            """UPDATE draw_rounds
            SET jackpot=jackpot+?,
                tickets=tickets+1
            WHERE id=?""",
            (
                ADD,
                draw["id"]
            )
        )

        if guildid and channelid:
            con.execute(
                """INSERT INTO draw_channels(
                    round_id,
                    guild_id,
                    channel_id
                ) VALUES(?,?,?)
                ON CONFLICT(round_id,guild_id)
                DO UPDATE
                SET channel_id=excluded.channel_id""",
                (
                    draw["id"],
                    guildid,
                    channelid
                )
            )

        draw=dict(
            con.execute(
                "SELECT * FROM draw_rounds WHERE id=?",
                (draw["id"],)
            ).fetchone()
        )

        ping=(
            draw["tickets"]>0
            and draw["tickets"]%PING_EVERY==0
        )

        return {
            "ok":True,
            "ticket":cur.lastrowid,
            "numbers":numbers,
            "thorn":thorn,
            "count":count+1,
            "ping":ping,
            "draw":draw
        }

def prize(
    numbers,
    thorn,
    winning,
    wthorn
):
    match=len(
        set(numbers)
        &set(winning)
    )

    same=thorn==wthorn

    if match==3 and same:
        return "jackpot"

    if match==3:
        return 10000

    if match==2 and same:
        return 2000

    if match==2:
        return 500

    return 0

def resolve():
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")

        found=con.execute(
            """SELECT *
            FROM draw_rounds
            WHERE status='open'
            ORDER BY id DESC LIMIT 1"""
        ).fetchone()

        if found is None:
            ensure(con)
            return None

        draw=dict(found)

        if draw["draws_at"]>time.time():
            return None

        if (
            not draw.get("numbers")
            or not draw.get("thorn")
        ):
            numbers,thorn=pick()

            con.execute(
                """UPDATE draw_rounds
                SET numbers=?,thorn=?
                WHERE id=?""",
                (
                    json.dumps(numbers),
                    thorn,
                    draw["id"]
                )
            )

            draw["numbers"]=json.dumps(numbers)
            draw["thorn"]=thorn

        winning=json.loads(
            draw["numbers"]
        )

        wthorn=int(
            draw["thorn"]
        )

        rows=[
            dict(row)
            for row in con.execute(
                """SELECT *
                FROM draw_tickets
                WHERE round_id=?
                ORDER BY id""",
                (draw["id"],)
            ).fetchall()
        ]

        jackpots=[]
        awards={}

        for row in rows:
            amount=prize(
                json.loads(
                    row["numbers"]
                ),
                row["thorn"],
                winning,
                wthorn
            )

            if amount=="jackpot":
                jackpots.append(
                    row["id"]
                )
            else:
                awards[
                    row["id"]
                ]=amount

        if jackpots:
            share,extra=divmod(
                draw["jackpot"],
                len(jackpots)
            )

            for index,ticketid in enumerate(
                jackpots
            ):
                awards[ticketid]=(
                    share
                    +(1 if index<extra else 0)
                )

        totals={}

        for row in rows:
            amount=int(
                awards.get(
                    row["id"],
                    0
                )
            )

            con.execute(
                """UPDATE draw_tickets
                SET payout=?
                WHERE id=?""",
                (
                    amount,
                    row["id"]
                )
            )

            if amount:
                if row["guild_id"] is None:
                    raise RuntimeError("draw ticket wallet guild missing")
                key=(
                    row["guild_id"],
                    row["user_id"]
                )
                totals[key]=(
                    totals.get(
                        key,
                        0
                    )
                    +amount
                )

        for (guild_id,uid),amount in totals.items():
            con.execute(
                "INSERT OR IGNORE INTO wallets(guild_id,user_id) VALUES(?,?)",
                (guild_id,uid)
            )

            con.execute(
                "UPDATE wallets SET roses=roses+? WHERE guild_id=? AND user_id=?",
                (
                    amount,
                    guild_id,
                    uid
                )
            )

        now=time.time()

        con.execute(
            """UPDATE draw_rounds
            SET status='resolved',
                resolved_at=?
            WHERE id=?""",
            (
                now,
                draw["id"]
            )
        )

        channels=[
            dict(row)
            for row in con.execute(
                """SELECT *
                FROM draw_channels
                WHERE round_id=?""",
                (draw["id"],)
            ).fetchall()
        ]

        nextpot=(
            BASE
            if jackpots
            else draw["jackpot"]
        )

        numbers,thorn=pick()
        nextat=nextdraw(now)

        con.execute(
            """INSERT INTO draw_rounds(
                draws_at,
                jackpot,
                numbers,
                thorn,
                created_at
            ) VALUES(?,?,?,?,?)""",
            (
                nextat,
                nextpot,
                json.dumps(numbers),
                thorn,
                now
            )
        )

        winners=[]

        for row in rows:
            amount=int(
                awards.get(
                    row["id"],
                    0
                )
            )

            if amount:
                winners.append({
                    "user_id":
                        row["user_id"],
                    "ticket":
                        row["id"],
                    "payout":
                        amount,
                    "jackpot":
                        row["id"] in jackpots
                })

        return {
            "id":draw["id"],
            "numbers":winning,
            "thorn":wthorn,
            "jackpot":draw["jackpot"],
            "tickets":len(rows),
            "jackpot_hits":len(jackpots),
            "winners":winners,
            "channels":channels,
            "nextpot":nextpot,
            "nextat":nextat
        }

def panel(uid,note=None):
    draw=current()
    mine,total=counts(uid,draw["id"])
    base=draw["jackpot"]-ADD*total
    lines=[]

    if note:
        lines.extend([
            note,
            ""
        ])

    lines.extend([
        (
            f'jackpot ⊹ **{base:,} roses {rosieemoji.ROSE} + {ADD:,} {rosieemoji.ROSE} × {total:,} 🎟️**'
        ),
        f"draw ⊹ "
        f"<t:{int(draw['draws_at'])}:F> "
        f"• <t:{int(draw['draws_at'])}:R>",
        f'ticket ⊹ **{COST:,} roses {rosieemoji.ROSE}**',
        f"your tickets ⊹ "
        f"**{mine} / {LIMIT}**",
        f"entries ⊹ "
        f"**{total:,}**",
        "",
        "pick **3 different numbers from 1–10**",
        "plus **1 thorn from 1–5**",
        "",
        "**payouts**",
        f"3 + thorn ⊹ **{draw['jackpot']:,} roses {rosieemoji.ROSE}**",
        '3 ⊹ **10,000 roses ' + rosieemoji.ROSE + '**',
        '2 + thorn ⊹ **2,000 roses ' + rosieemoji.ROSE + '**',
        '2 ⊹ **500 roses ' + rosieemoji.ROSE + '**'
    ])

    previous=last()

    if previous:
        lines.extend([
            "",
            f"last draw ⊹ "
            f"**{combo(json.loads(previous['numbers']),previous['thorn'])}**"
        ])

    return discord.Embed(
        title=rosieemoji.ROSE + " rosie's draw",
        description="\n".join(lines),
        color=discord.Color.dark_red()
    )



def ticketembed(uid):
    draw=current()

    rows=tickets(
        uid,
        draw["id"]
    )

    if rows:
        lines=[
            f"`{index}.` "
            f"**{combo(json.loads(row['numbers']),row['thorn'])}**"
            for index,row in enumerate(
                rows,
                1
            )
        ]
    else:
        lines=[
            "no tickets yet"
        ]

    return discord.Embed(
        title="📜 your tickets",
        description=(
            "\n".join(lines)
            +f"\n\n"
            f"<t:{int(draw['draws_at'])}:R>"
        ),
        color=discord.Color.dark_red()
    )

def testembed():
    draw=current()
    rows=alltickets(
        draw["id"]
    )

    lines=[
        f"round ⊹ **#{draw['id']}**",
        f"draw ⊹ "
        f"<t:{int(draw['draws_at'])}:F>",
        f"winning ⊹ "
        f"**{combo(json.loads(draw['numbers']),draw['thorn'])}**",
        f"entries ⊹ "
        f"**{len(rows):,}**"
    ]

    if rows:
        lines.extend([
            "",
            "**tickets**"
        ])

        for index,row in enumerate(
            rows,
            1
        ):
            line=(
                f"`{index}.` "
                f"<@{row['user_id']}> ⊹ "
                f"**{combo(json.loads(row['numbers']),row['thorn'])}**"
            )

            test="\n".join(
                lines+[line]
            )

            if len(test)>3900:
                left=len(rows)-index+1

                lines.append(
                    f"+{left:,} more"
                )

                break

            lines.append(
                line
            )

    else:
        lines.extend([
            "",
            "no tickets yet"
        ])

    return discord.Embed(
        description="\n".join(lines),
        color=discord.Color.dark_red()
    )


def err(result):
    if result["reason"]=="broke":
        return (
            f"broke broski you need {result['need']:,} more {rosieemoji.ROSE}"
        )

    if result["reason"]=="limit":
        return (
            f"ur at the "
            f"{LIMIT} ticket limit"
        )

    if result["reason"]=="duplicate":
        return (
            "you already bought that exact ticket"
        )

    if result["reason"]=="drawing":
        return (
            "rosie is drawing rn "
            "try again in a sec"
        )

    return (
        "pick 3 different numbers from 1-10 "
        "and a thorn from 1-5"
    )

async def refresh(message,cog,uid):
    if message is None:
        return

    try:
        await message.edit(
            embed=panel(uid),
            view=DrawView(cog)
        )
    except discord.HTTPException:
        pass

async def drawroutes(bot):
    routes=[]
    configured=set()

    for guild in bot.guilds:
        data=guildconfig.draw(
            guild.id
        )

        channel_id=data[
            "draw_channel_id"
        ]

        if not channel_id:
            continue

        configured.add(
            guild.id
        )

        channel=guild.get_channel(
            channel_id
        )

        if channel is None:
            channel=bot.get_channel(
                channel_id
            )

        if channel is None:
            try:
                channel=await bot.fetch_channel(
                    channel_id
                )

            except discord.HTTPException:
                channel=None

        if channel is None:
            continue

        routes.append({
            "guild_id":guild.id,
            "channel":channel,
            "role_id":
                data["draw_ping_role_id"],
            "pings":
                bool(
                    data["draw_pings_enabled"]
                )
        })

    legacy_id=legacyconfig.DRAW_CHANNEL_ID

    legacy=(
        bot.get_channel(
            legacy_id
        )
        if legacy_id
        else None
    )

    if (
        legacy is None
        and legacy_id
    ):
        try:
            legacy=await bot.fetch_channel(
                legacy_id
            )

        except discord.HTTPException:
            legacy=None

    if legacy is not None:
        guild=getattr(
            legacy,
            "guild",
            None
        )

        guild_id=getattr(
            guild,
            "id",
            None
        )

        if guild_id not in configured:
            routes.append({
                "guild_id":guild_id,
                "channel":legacy,
                "role_id":
                    legacyconfig.DRAW_ROLE_ID,
                "pings":bool(
                    legacyconfig.DRAW_ROLE_ID
                )
            })

    unique=[]
    seen=set()

    for route in routes:
        channel_id=route[
            "channel"
        ].id

        if channel_id in seen:
            continue

        seen.add(
            channel_id
        )

        unique.append(
            route
        )

    return unique


async def pingdraw(bot,draw):
    routes=await drawroutes(
        bot
    )

    sent=False

    for route in routes:
        role_id=route[
            "role_id"
        ]

        ping=(
            route["pings"]
            and role_id
        )

        prefix=(
            f"<@&{role_id}> ‼️ "
            if ping
            else "‼️ "
        )

        text=(
            f"{prefix}**draw update**\n\njackpot ⊹ **{draw['jackpot']:,} roses {rosieemoji.ROSE}**\nentries ⊹ **{draw['tickets']:,}**\nenter ⊹ **/draw**"
        )

        try:
            await route[
                "channel"
            ].send(
                text,
                allowed_mentions=
                    discord.AllowedMentions(
                        everyone=False,
                        users=False,
                        roles=bool(
                            ping
                        )
                    )
            )

            sent=True

        except discord.HTTPException:
            pass

    return sent

class PickModal(discord.ui.Modal):
    def __init__(
        self,
        cog,
        uid,
        public
    ):
        super().__init__(
            title=rosieemoji.ROSE + " rosie's draw"
        )

        self.cog=cog
        self.uid=uid
        self.public=public

        self.numbers=discord.ui.TextInput(
            label='3 numbers',
            placeholder="2 6 9",
            min_length=5,
            max_length=8
        )

        self.thorn=discord.ui.TextInput(
            label="thorn 1-5",
            placeholder="3",
            min_length=1,
            max_length=1
        )

        self.add_item(
            self.numbers
        )

        self.add_item(
            self.thorn
        )

    async def on_submit(
        self,
        it:discord.Interaction
    ):
        if it.user.id!=self.uid:
            await it.response.send_message(
                "nuh uh",
                ephemeral=True
            )
            return

        numbers=parse(
            self.numbers.value
        )

        try:
            thorn=int(
                self.thorn.value
            )
        except ValueError:
            thorn=0

        result=buy(
            self.uid,
            numbers or [],
            thorn,
            it.guild.id
            if it.guild
            else None,
            it.channel.id
            if it.channel
            else None
        )

        if not result["ok"]:
            await it.response.send_message(
                err(result),
                ephemeral=True
            )
            return

        game.touch(
            self.uid
        )

        if result.get("ping"):
            asyncio.create_task(
                pingdraw(
                    self.cog.bot,
                    result["draw"]
                )
            )

        await it.response.send_message(
            f"🎟️ "
            f"**{combo(result['numbers'],result['thorn'])}**",
            ephemeral=True
        )

        await refresh(
            self.public,
            self.cog,
            self.uid
        )


class QuickView(discord.ui.View):
    def __init__(
        self,
        cog,
        uid,
        public
    ):
        super().__init__(
            timeout=60
        )

        self.cog=cog
        self.uid=uid
        self.public=public

    async def check(
        self,
        it
    ):
        if it.user.id!=self.uid:
            await it.response.send_message(
                "nuh uh",
                ephemeral=True
            )
            return False

        return True

    @discord.ui.button(
        emoji="✅",
        style=discord.ButtonStyle.success
    )
    async def yes(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        if not await self.check(it):
            return

        result=buy(
            self.uid,
            guildid=(
                it.guild.id
                if it.guild
                else None
            ),
            channelid=(
                it.channel.id
                if it.channel
                else None
            )
        )

        if not result["ok"]:
            await it.response.edit_message(
                embed=discord.Embed(
                    description=err(result),
                    color=discord.Color.dark_red()
                ),
                view=None
            )
            return

        game.touch(
            self.uid
        )

        if result.get("ping"):
            asyncio.create_task(
                pingdraw(
                    self.cog.bot,
                    result["draw"]
                )
            )

        await it.response.edit_message(
            embed=discord.Embed(
                title="🎟️ ticket",
                description=(
                    f"**{combo(result['numbers'],result['thorn'])}**"
                ),
                color=discord.Color.dark_red()
            ),
            view=None
        )

        await refresh(
            self.public,
            self.cog,
            self.uid
        )

    @discord.ui.button(
        emoji="❌",
        style=discord.ButtonStyle.secondary
    )
    async def no(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        if not await self.check(it):
            return

        await it.response.edit_message(
            content="❌",
            embed=None,
            view=None
        )


class DrawView(discord.ui.View):
    def __init__(
        self,
        cog
    ):
        super().__init__(
            timeout=600
        )

        self.cog=cog

    @discord.ui.button(
        emoji="🎟️",
        style=discord.ButtonStyle.danger
    )
    async def quick(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        draw=current()
        mine,_=counts(
            it.user.id,
            draw["id"]
        )

        if mine>=LIMIT:
            await it.response.send_message(
                f"ur at the {LIMIT} ticket limit",
                ephemeral=True
            )
            return

        await it.response.send_message(
            embed=discord.Embed(
                title="🎟️ quick pick",
                description=(
                    f'**{COST:,} roses {rosieemoji.ROSE}**\nrosie picks the numbers'
                ),
                color=discord.Color.dark_red()
            ),
            view=QuickView(
                self.cog,
                it.user.id,
                it.message
            ),
            ephemeral=True
        )

    @discord.ui.button(
        emoji="✏️",
        style=discord.ButtonStyle.secondary
    )
    async def manual(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        draw=current()
        mine,_=counts(
            it.user.id,
            draw["id"]
        )

        if mine>=LIMIT:
            await it.response.send_message(
                f"ur at the {LIMIT} ticket limit",
                ephemeral=True
            )
            return

        await it.response.send_modal(
            PickModal(
                self.cog,
                it.user.id,
                it.message
            )
        )

    @discord.ui.button(
        emoji="📜",
        style=discord.ButtonStyle.secondary
    )
    async def mine(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        await it.response.send_message(
            embed=ticketembed(
                it.user.id
            ),
            ephemeral=True
        )

class Draw(commands.Cog):
    def __init__(
        self,
        bot
    ):
        self.bot=bot
        self.registry_done=False
        self.lock=asyncio.Lock()

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
                if item.get("name")=="draw"
                and int(item.get("type",1))==1
            ),
            None
        )

        payload={
            "name":"draw",
            "description":"open rosie's draw",
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
            "draw command registry ✓"
        )

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            await self.registry()

        except Exception as error:
            print(
                f"draw registry failed ⊹ {error}"
            )

    def cog_unload(self):
        self.clock.cancel()

    async def announce(
        self,
        result
    ):
        winning=combo(
            result["numbers"],
            result["thorn"]
        )

        jackpot=[
            item
            for item in result["winners"]
            if item["jackpot"]
        ]

        other=[
            item
            for item in result["winners"]
            if not item["jackpot"]
        ]

        lines=[
            f"winning numbers ⊹ "
            f"**{winning}**",

            f"tickets ⊹ "
            f"**{result['tickets']:,}**"
        ]

        if jackpot:
            users=list(
                dict.fromkeys(
                    f"<@{item['user_id']}>"
                    for item in jackpot
                )
            )

            lines.extend([
                f"jackpot ⊹ **{result['jackpot']:,} roses {rosieemoji.ROSE}**",

                f"winner"
                f"{'s' if len(users)!=1 else ''} "
                f"⊹ "
                +" • ".join(users)
            ])

        else:
            lines.extend([
                "jackpot ⊹ nobody got it lol",

                f"carryover ⊹ **{result['nextpot']:,} roses {rosieemoji.ROSE}**"
            ])

        if other:
            lines.append(
                f"other winning tickets ⊹ "
                f"**{len(other):,}**"
            )

        embed=discord.Embed(
            title=rosieemoji.ROSE + ' the draw',
            description="\n".join(lines),
            color=discord.Color.dark_red()
        )

        routes=await drawroutes(
            self.bot
        )

        for route in routes:
            try:
                await route[
                    "channel"
                ].send(
                    embed=embed,
                    allowed_mentions=
                        discord.AllowedMentions(
                            users=True,
                            roles=False,
                            everyone=False
                        )
                )

            except discord.HTTPException:
                pass

    @tasks.loop(
        seconds=15
    )
    async def clock(self):
        try:
            async with self.lock:
                result=resolve()

            if result:
                await self.announce(
                    result
                )

        except Exception as error:
            print(
                f"draw clock warning: "
                f"{error}"
            )

    @clock.before_loop
    async def ready(self):
        await self.bot.wait_until_ready()

    @app_commands.command(
        name="draw",
        description="open rosie's draw"
    )
    @app_commands.guild_only()
    async def draw(
        self,
        it:discord.Interaction
    ):
        game.touch(
            it.user.id
        )

        draw=current()

        watch(
            draw["id"],
            it.guild.id,
            it.channel.id
        )

        await it.response.send_message(
            embed=panel(
                it.user.id
            ),
            view=DrawView(
                self
            )
        )

async def setup(bot):
    guildconfig.init()
    init()

    await bot.add_cog(
        Draw(bot)
    )
