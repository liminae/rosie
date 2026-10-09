import asyncio
import hashlib
import sqlite3
import time

from core import database

UPDATES=(
    (
        "🧪 brew reminders",
        (
            "`/ping` now has a **brew** reminder toggle.",
            "turn it on to get a DM when your final rose tonic or knowledge charge is used."
        )
    ),
    (
        "🎨 embed colors",
        (
            "`/redeem` now has **embed color** changes for **1 ring** 💍.",
            "enter a hex color and preview it before paying. one purchase = one change.",
            "want rosie red again? use **#992D22**."
        )
    ),
)

PENDING=set()

def connect():
    con=sqlite3.connect(
        database.FILE,
        timeout=10
    )
    con.row_factory=sqlite3.Row
    return con

def token(update):
    title,lines=update

    text="\n".join(
        (
            title,
            *lines
        )
    )

    return hashlib.sha256(
        text.encode()
    ).hexdigest()

def init():
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS update_notices(
            user_id INTEGER NOT NULL,
            token TEXT NOT NULL,
            seen_at REAL NOT NULL,
            PRIMARY KEY(user_id,token)
        )""")

def seen(user_id):
    with connect() as con:
        rows=con.execute(
            """SELECT token
            FROM update_notices
            WHERE user_id=?""",
            (user_id,)
        ).fetchall()

    return {
        row["token"]
        for row in rows
    }

def claim(user_id):
    old=seen(
        user_id
    )

    fresh=[]

    for update in UPDATES:
        mark=token(
            update
        )

        key=(
            int(user_id),
            mark
        )

        if (
            mark not in old
            and key not in PENDING
        ):
            PENDING.add(
                key
            )

            fresh.append(
                update
            )

    return fresh

def release(user_id,items):
    for update in items:
        PENDING.discard(
            (
                int(user_id),
                token(update)
            )
        )

def mark(user_id,items):
    now=time.time()

    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        for update in items:
            con.execute(
                """INSERT OR IGNORE INTO update_notices(
                    user_id,token,seen_at
                ) VALUES(?,?,?)""",
                (
                    user_id,
                    token(update),
                    now
                )
            )

    release(
        user_id,
        items
    )

def description(items):
    sections=[]

    for title,lines in items:
        sections.append(
            f"**{title}**\n"
            +"\n".join(
                f"⊹ {line}"
                for line in lines
            )
        )

    return "\n\n".join(
        sections
    )

def embed(items):
    import discord

    return discord.Embed(
        title="🌹 rosie update",
        description=description(
            items
        ),
        color=discord.Color.dark_red()
    )

async def deliver(it,items):
    try:
        for _ in range(
            300
        ):
            if it.response.is_done():
                break

            await asyncio.sleep(
                .1
            )

        if not it.response.is_done():
            release(
                it.user.id,
                items
            )

            return

        await it.followup.send(
            embed=embed(
                items
            ),
            ephemeral=True
        )

        mark(
            it.user.id,
            items
        )

    except asyncio.CancelledError:
        release(
            it.user.id,
            items
        )

        raise

    except Exception as error:
        release(
            it.user.id,
            items
        )

        print(
            f"update notice error ⊹ {error}"
        )

def queue(it):
    items=claim(
        it.user.id
    )

    if items:
        asyncio.create_task(
            deliver(
                it,
                items
            )
        )
