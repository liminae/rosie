import sys
sys.dont_write_bytecode=True

import secrets
import sqlite3
import time
from pathlib import Path

DB=(
    Path(__file__).resolve().parents[1]
    /"rosie.db"
)

WIDTH=360000
HEIGHT=560000

BIRD_X=90000
BIRD_W=26000
BIRD_H=20000

GRAVITY=380
FLAP=-6200

PIPE_W=62000
GAP_MIN=124000
GAP_RANGE=40001
PIPE_SPEED=2600
PIPE_SPACING=250000
PIPE_FIRST=430000

CENTER_MIN=140000
CENTER_RANGE=280000

TOKEN_FIRST=3
TOKEN_EVERY=12
TOKEN_RADIUS=10000
TOKEN_EDGE=26000
TOKEN_BOOST=10

FPS=60
MAX_TICKS=FPS*60*30

def connect():
    con=sqlite3.connect(
        DB,
        timeout=15
    )

    con.row_factory=sqlite3.Row

    return con

def init():
    with connect() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS soaring_runs(
                run_id TEXT PRIMARY KEY,
                guild_id INTEGER,
                user_id INTEGER NOT NULL,
                seed INTEGER NOT NULL,
                started_at REAL NOT NULL,
                settled INTEGER NOT NULL DEFAULT 0,
                score INTEGER,
                reward INTEGER
            )"""
        )

        cols={
            row["name"]
            for row in con.execute(
                "PRAGMA table_info(soaring_runs)"
            )
        }

        if "guild_id" not in cols:
            con.execute(
                "ALTER TABLE soaring_runs ADD COLUMN guild_id INTEGER"
            )

        con.execute(
            """UPDATE soaring_runs
            SET settled=1,
                score=COALESCE(score,0),
                reward=COALESCE(reward,0)
            WHERE guild_id IS NULL
            AND settled=0"""
        )

        con.execute(
            """DELETE FROM soaring_runs
            WHERE started_at<?""",
            (
                time.time()
                -172800,
            )
        )

def start(guild_id,user_id):
    run_id=secrets.token_urlsafe(
        24
    )

    seed=secrets.randbits(
        32
    )

    now=time.time()

    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        con.execute(
            """UPDATE soaring_runs
            SET settled=1,
                score=COALESCE(score,0),
                reward=COALESCE(reward,0)
            WHERE user_id=?
            AND settled=0""",
            (
                user_id,
            )
        )

        con.execute(
            """INSERT INTO soaring_runs(
                run_id,
                guild_id,
                user_id,
                seed,
                started_at,
                settled
            ) VALUES(?,?,?,?,?,0)""",
            (
                run_id,
                guild_id,
                user_id,
                seed,
                now
            )
        )

    return {
        "run_id":
            run_id,

        "seed":
            seed
    }

def center(index,cache):
    while len(
        cache["centers"]
    )<=index:
        cache["state"]=(
            1664525*cache["state"]
            +1013904223
        )&0xffffffff

        state=cache["state"]

        center_value=(
            CENTER_MIN
            +(
                state
                *CENTER_RANGE
            )//4294967296
        )

        gap_value=(
            GAP_MIN
            +(
                (state>>8)
                %GAP_RANGE
            )
        )

        cache["centers"].append(
            center_value
        )

        cache["gaps"].append(
            gap_value
        )

    return cache[
        "centers"
    ][index]

def opening(index,cache):
    center(
        index,
        cache
    )

    return cache[
        "gaps"
    ][index]


def token(index,seed,cache):
    if (
        index<TOKEN_FIRST
        or (index-TOKEN_FIRST)%TOKEN_EVERY
    ):
        return None

    middle=center(
        index,
        cache
    )
    size=opening(
        index,
        cache
    )

    mixed=(
        int(seed)
        ^(
            (index+1)
            *0x9E3779B9
        )
    )&0xffffffff

    top=(mixed&1)==0

    return (
        middle-size//2+TOKEN_EDGE
        if top
        else middle+size//2-TOKEN_EDGE
    )

def simulate(seed,flaps):
    flapset=set(
        flaps
    )

    y=HEIGHT//2
    velocity=0

    score=0
    credits=0
    boost=0
    next_pipe=0
    collected=set()

    cache={
        "state":int(seed)&0xffffffff,
        "centers":[],
        "gaps":[]
    }

    bird_left=(
        BIRD_X
        -BIRD_W//2
    )

    bird_right=(
        BIRD_X
        +BIRD_W//2
    )

    for tick in range(
        MAX_TICKS
    ):
        if tick in flapset:
            velocity=FLAP

        velocity+=GRAVITY
        y+=velocity

        top=(
            y
            -BIRD_H//2
        )

        bottom=(
            y
            +BIRD_H//2
        )

        if (
            top<=0
            or bottom>=HEIGHT
        ):
            return (
                score,
                credits,
                tick+1
            )

        for index in range(
            next_pipe,
            next_pipe+4
        ):
            x=(
                PIPE_FIRST
                +index*PIPE_SPACING
                -PIPE_SPEED*tick
            )

            overlap=(
                bird_right>x
                and bird_left<x+PIPE_W
            )

            if overlap:
                middle=center(
                    index,
                    cache
                )

                size=opening(
                    index,
                    cache
                )

                gap_top=(
                    middle
                    -size//2
                )

                gap_bottom=(
                    middle
                    +size//2
                )

                if (
                    top<gap_top
                    or bottom>gap_bottom
                ):
                    return (
                        score,
                        credits,
                        tick+1
                    )

            token_y=token(
                index,
                seed,
                cache
            )

            if (
                token_y is None
                or index in collected
            ):
                continue

            token_x=(
                x
                +PIPE_W//2
            )

            if (
                abs(token_x-BIRD_X)
                <=BIRD_W//2+TOKEN_RADIUS
                and abs(token_y-y)
                <=BIRD_H//2+TOKEN_RADIUS
            ):
                collected.add(
                    index
                )
                boost=TOKEN_BOOST

        while True:
            x=(
                PIPE_FIRST
                +next_pipe*PIPE_SPACING
                -PIPE_SPEED*tick
            )

            if x+PIPE_W>=bird_left:
                break

            score+=1

            if boost>0:
                credits+=2
                boost-=1
            else:
                credits+=1

            next_pipe+=1

    return (
        None,
        None,
        MAX_TICKS
    )

def finish(
    guild_id,
    user_id,
    run_id,
    raw_flaps
):
    if (
        not isinstance(
            run_id,
            str
        )
        or not run_id
        or not isinstance(
            raw_flaps,
            list
        )
        or len(raw_flaps)>MAX_TICKS
    ):
        return {
            "ok":False,
            "reason":"bad run"
        }

    try:
        flaps=sorted(
            {
                int(value)
                for value in raw_flaps
            }
        )

    except Exception:
        return {
            "ok":False,
            "reason":"bad flaps"
        }

    if any(
        tick<0
        or tick>=MAX_TICKS
        for tick in flaps
    ):
        return {
            "ok":False,
            "reason":"bad flaps"
        }

    with connect() as con:
        row=con.execute(
            """SELECT *
            FROM soaring_runs
            WHERE run_id=?
            AND guild_id=?
            AND user_id=?""",
            (
                run_id,
                guild_id,
                user_id
            )
        ).fetchone()

    if row is None:
        return {
            "ok":False,
            "reason":"run not found"
        }

    if row["settled"]:
        return {
            "ok":True,
            "score":
                int(
                    row["score"]
                    or 0
                ),
            "reward":
                int(
                    row["reward"]
                    or 0
                ),
            "new":False
        }

    score,credits,ticks=simulate(
        int(row["seed"]),
        flaps
    )

    if score is None:
        return {
            "ok":False,
            "reason":"run unfinished"
        }

    elapsed=(
        time.time()
        -float(
            row["started_at"]
        )
    )

    minimum=(
        ticks/FPS
    )

    if elapsed+2.5<minimum:
        return {
            "ok":False,
            "reason":"run too fast"
        }

    reward=(
        credits//10
    )

    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        current=con.execute(
            """SELECT settled,score,reward
            FROM soaring_runs
            WHERE run_id=?
            AND guild_id=?
            AND user_id=?""",
            (
                run_id,
                guild_id,
                user_id
            )
        ).fetchone()

        if current is None:
            return {
                "ok":False,
                "reason":"run not found"
            }

        if current["settled"]:
            return {
                "ok":True,
                "score":
                    int(
                        current["score"]
                        or 0
                    ),
                "reward":
                    int(
                        current["reward"]
                        or 0
                    ),
                "new":False
            }

        con.execute(
            """INSERT OR IGNORE INTO wallets(guild_id,user_id)
            VALUES(?,?)""",
            (
                guild_id,
                user_id
            )
        )

        if reward:
            con.execute(
                """UPDATE wallets
                SET roses=roses+?
                WHERE guild_id=?
                AND user_id=?""",
                (
                    reward,
                    guild_id,
                    user_id
                )
            )

        con.execute(
            """UPDATE soaring_runs
            SET settled=1,
                score=?,
                reward=?
            WHERE run_id=?
            AND guild_id=?
            AND user_id=?""",
            (
                score,
                reward,
                run_id,
                guild_id,
                user_id
            )
        )

    return {
        "ok":True,
        "score":
            score,
        "reward":
            reward,
        "new":True
    }
