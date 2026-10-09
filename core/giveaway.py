import secrets
import sqlite3
import time

from core import database

KINDS={
    "commands",
    "command",
    "distinct_commands",
    "active_days",
    "season_xp",
    "season_tier",
    "roses",
    "rings",
    "role",
    "not_role",
    "joined_days",
    "account_days",
    "previous_winner"
}


def connect():
    con=sqlite3.connect(
        database.FILE,
        timeout=15
    )
    con.row_factory=sqlite3.Row
    return con


def init():
    with connect() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS giveaways(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER,
                title TEXT NOT NULL,
                prize TEXT NOT NULL,
                winners INTEGER NOT NULL DEFAULT 1,
                entry_emoji TEXT NOT NULL DEFAULT '🎁',
                ping_role_id INTEGER,
                status TEXT NOT NULL DEFAULT 'draft',
                created_by INTEGER NOT NULL,
                created_at REAL NOT NULL,
                ends_at REAL,
                posted_at REAL,
                closed_at REAL
            )"""
        )

        con.execute(
            """CREATE INDEX IF NOT EXISTS giveaways_guild_idx
            ON giveaways(guild_id,status,created_at)"""
        )

        con.execute(
            """CREATE TABLE IF NOT EXISTS giveaway_requirements(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                giveaway_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                value TEXT,
                detail TEXT,
                position INTEGER NOT NULL DEFAULT 0
            )"""
        )

        con.execute(
            """CREATE INDEX IF NOT EXISTS giveaway_requirements_idx
            ON giveaway_requirements(giveaway_id,position,id)"""
        )

        con.execute(
            """CREATE TABLE IF NOT EXISTS giveaway_entries(
                giveaway_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                entered_at REAL NOT NULL,
                PRIMARY KEY(giveaway_id,user_id)
            )"""
        )

        con.execute(
            """CREATE TABLE IF NOT EXISTS giveaway_winners(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                giveaway_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                round INTEGER NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                drawn_at REAL NOT NULL
            )"""
        )

        con.execute(
            """CREATE INDEX IF NOT EXISTS giveaway_winners_idx
            ON giveaway_winners(giveaway_id,active,id)"""
        )


def create(
    guild_id,
    channel_id,
    title,
    prize,
    winners,
    created_by,
    ends_at=None,
    ping_role_id=None,
    entry_emoji="🎁"
):
    init()

    guild_id=int(guild_id)
    channel_id=int(channel_id)
    winners=int(winners)
    created_by=int(created_by)
    title=str(title).strip()
    prize=str(prize).strip()
    entry_emoji=str(entry_emoji or "🎁").strip()

    if guild_id<1 or channel_id<1 or created_by<1:
        raise ValueError("invalid giveaway target")

    if winners<1:
        raise ValueError("winners must be at least 1")

    if not title or not prize:
        raise ValueError("title and prize required")

    if ends_at is not None:
        ends_at=float(ends_at)

    if ping_role_id is not None:
        ping_role_id=int(ping_role_id)

    with connect() as con:
        cur=con.execute(
            """INSERT INTO giveaways(
                guild_id,
                channel_id,
                title,
                prize,
                winners,
                entry_emoji,
                ping_role_id,
                created_by,
                created_at,
                ends_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                guild_id,
                channel_id,
                title,
                prize,
                winners,
                entry_emoji,
                ping_role_id,
                created_by,
                time.time(),
                ends_at
            )
        )

        gid=cur.lastrowid

    return get(gid)


def get(giveaway_id):
    init()

    with connect() as con:
        row=con.execute(
            "SELECT * FROM giveaways WHERE id=?",
            (int(giveaway_id),)
        ).fetchone()

    return dict(row) if row else None


def listguild(guild_id,limit=25):
    init()

    with connect() as con:
        rows=con.execute(
            """SELECT *
            FROM giveaways
            WHERE guild_id=?
            ORDER BY id DESC
            LIMIT ?""",
            (
                int(guild_id),
                int(limit)
            )
        ).fetchall()

    return [dict(row) for row in rows]


def openrows():
    init()

    with connect() as con:
        rows=con.execute(
            """SELECT *
            FROM giveaways
            WHERE status='open'
            AND message_id IS NOT NULL"""
        ).fetchall()

    return [dict(row) for row in rows]


def setmessage(giveaway_id,message_id):
    with connect() as con:
        con.execute(
            """UPDATE giveaways
            SET message_id=?,
                status='open',
                posted_at=?
            WHERE id=?""",
            (
                int(message_id),
                time.time(),
                int(giveaway_id)
            )
        )

    return get(giveaway_id)


def setping(giveaway_id,role_id):
    with connect() as con:
        con.execute(
            "UPDATE giveaways SET ping_role_id=? WHERE id=?",
            (
                int(role_id) if role_id is not None else None,
                int(giveaway_id)
            )
        )

    return get(giveaway_id)


def setstatus(giveaway_id,status):
    status=str(status).strip().casefold()

    if status not in {"draft","open","closed","cancelled"}:
        raise ValueError("invalid giveaway status")

    with connect() as con:
        con.execute(
            """UPDATE giveaways
            SET status=?,
                closed_at=?
            WHERE id=?""",
            (
                status,
                time.time() if status in {"closed","cancelled"} else None,
                int(giveaway_id)
            )
        )

    return get(giveaway_id)


def addrequirement(
    giveaway_id,
    kind,
    value=None,
    detail=None,
    position=None
):
    kind=str(kind).strip().casefold()

    if kind not in KINDS:
        raise ValueError("invalid giveaway requirement")

    if value is not None:
        value=str(value).strip()

    if detail is not None:
        detail=str(detail).strip()

    with connect() as con:
        if position is None:
            row=con.execute(
                """SELECT COALESCE(MAX(position),-1)+1 AS n
                FROM giveaway_requirements
                WHERE giveaway_id=?""",
                (int(giveaway_id),)
            ).fetchone()

            position=int(row["n"])

        cur=con.execute(
            """INSERT INTO giveaway_requirements(
                giveaway_id,
                kind,
                value,
                detail,
                position
            ) VALUES(?,?,?,?,?)""",
            (
                int(giveaway_id),
                kind,
                value,
                detail,
                int(position)
            )
        )

        rid=cur.lastrowid

    return requirement(rid)


def requirement(requirement_id):
    with connect() as con:
        row=con.execute(
            "SELECT * FROM giveaway_requirements WHERE id=?",
            (int(requirement_id),)
        ).fetchone()

    return dict(row) if row else None


def requirements(giveaway_id):
    init()

    with connect() as con:
        rows=con.execute(
            """SELECT *
            FROM giveaway_requirements
            WHERE giveaway_id=?
            ORDER BY position,id""",
            (int(giveaway_id),)
        ).fetchall()

    return [dict(row) for row in rows]


def removerequirement(requirement_id):
    with connect() as con:
        cur=con.execute(
            "DELETE FROM giveaway_requirements WHERE id=?",
            (int(requirement_id),)
        )

    return cur.rowcount==1


def enter(giveaway_id,user_id):
    data=get(giveaway_id)

    if data is None or data["status"]!="open":
        return False

    if data["ends_at"] is not None and time.time()>=float(data["ends_at"]):
        return False

    with connect() as con:
        con.execute(
            """INSERT OR IGNORE INTO giveaway_entries(
                giveaway_id,user_id,entered_at
            ) VALUES(?,?,?)""",
            (
                int(giveaway_id),
                int(user_id),
                time.time()
            )
        )

    return True


def leave(giveaway_id,user_id):
    with connect() as con:
        cur=con.execute(
            """DELETE FROM giveaway_entries
            WHERE giveaway_id=?
            AND user_id=?""",
            (
                int(giveaway_id),
                int(user_id)
            )
        )

    return cur.rowcount==1


def entries(giveaway_id):
    with connect() as con:
        rows=con.execute(
            """SELECT user_id,entered_at
            FROM giveaway_entries
            WHERE giveaway_id=?
            ORDER BY entered_at,user_id""",
            (int(giveaway_id),)
        ).fetchall()

    return [dict(row) for row in rows]


def entrycount(giveaway_id):
    with connect() as con:
        row=con.execute(
            """SELECT COUNT(*) AS n
            FROM giveaway_entries
            WHERE giveaway_id=?""",
            (int(giveaway_id),)
        ).fetchone()

    return int(row["n"])


def winnerrows(giveaway_id,active_only=False):
    sql=(
        """SELECT * FROM giveaway_winners
        WHERE giveaway_id=? AND active=1
        ORDER BY id"""
        if active_only
        else
        """SELECT * FROM giveaway_winners
        WHERE giveaway_id=?
        ORDER BY id"""
    )

    with connect() as con:
        rows=con.execute(
            sql,
            (int(giveaway_id),)
        ).fetchall()

    return [dict(row) for row in rows]


def previouswinner(guild_id,user_id):
    with connect() as con:
        row=con.execute(
            """SELECT 1
            FROM giveaway_winners w
            JOIN giveaways g ON g.id=w.giveaway_id
            WHERE g.guild_id=?
            AND w.user_id=?
            AND w.active=1
            LIMIT 1""",
            (
                int(guild_id),
                int(user_id)
            )
        ).fetchone()

    return row is not None


def recordwinners(giveaway_id,user_ids,round_number=None):
    user_ids=[int(user_id) for user_id in user_ids]

    if not user_ids:
        return []

    if round_number is None:
        with connect() as con:
            row=con.execute(
                """SELECT COALESCE(MAX(round),0)+1 AS n
                FROM giveaway_winners
                WHERE giveaway_id=?""",
                (int(giveaway_id),)
            ).fetchone()

            round_number=int(row["n"])

    with connect() as con:
        now=time.time()

        for user_id in user_ids:
            con.execute(
                """INSERT INTO giveaway_winners(
                    giveaway_id,user_id,round,active,drawn_at
                ) VALUES(?,?,?,1,?)""",
                (
                    int(giveaway_id),
                    user_id,
                    int(round_number),
                    now
                )
            )

    return winnerrows(giveaway_id,True)


def deactivatewinner(winner_id):
    with connect() as con:
        cur=con.execute(
            """UPDATE giveaway_winners
            SET active=0
            WHERE id=?
            AND active=1""",
            (int(winner_id),)
        )

    return cur.rowcount==1


def choose(user_ids,count,exclude=None):
    pool=[
        int(user_id)
        for user_id in user_ids
        if int(user_id) not in set(exclude or ())
    ]

    count=min(
        int(count),
        len(pool)
    )

    if count<1:
        return []

    return secrets.SystemRandom().sample(
        pool,
        count
    )
