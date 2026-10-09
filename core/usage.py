import sqlite3
import statistics
import time
from datetime import datetime

from core import game
from core import policy

SKIP={"usage","give","take","control","roses"}
WATCH_KEEP=14*86400

def connect():
    con=sqlite3.connect(
        game.DB,
        timeout=10
    )
    con.row_factory=sqlite3.Row
    return con

def init():
    now=time.time()

    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS usage_users(
            user_id INTEGER PRIMARY KEY,
            total INTEGER NOT NULL DEFAULT 0,
            first_at REAL NOT NULL,
            last_at REAL NOT NULL
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS usage_days(
            user_id INTEGER NOT NULL,
            day TEXT NOT NULL,
            total INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id,day)
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS usage_meta(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS usage_commands(
            command TEXT PRIMARY KEY,
            total INTEGER NOT NULL DEFAULT 0,
            first_at REAL NOT NULL,
            last_at REAL NOT NULL
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS usage_command_days(
            command TEXT NOT NULL,
            day TEXT NOT NULL,
            total INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(command,day)
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS usage_command_users(
            command TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            total INTEGER NOT NULL DEFAULT 0,
            first_at REAL NOT NULL,
            last_at REAL NOT NULL,
            PRIMARY KEY(command,user_id)
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS usage_watch_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            at REAL NOT NULL,
            user_id INTEGER NOT NULL,
            command TEXT NOT NULL
        )""")

        con.execute(
            "CREATE INDEX IF NOT EXISTS usage_watch_at "
            "ON usage_watch_events(at)"
        )

        con.execute(
            "CREATE INDEX IF NOT EXISTS usage_watch_user_at "
            "ON usage_watch_events(user_id,at)"
        )

        con.execute(
            "INSERT OR IGNORE INTO usage_meta(key,value) "
            "VALUES('started_at',?)",
            (str(now),)
        )

        con.execute(
            "INSERT OR IGNORE INTO usage_meta(key,value) "
            "VALUES('watch_started_at',?)",
            (str(now),)
        )

        con.execute(
            "DELETE FROM usage_watch_events WHERE at<?",
            (now-WATCH_KEEP,)
        )

def stamp(value):
    if value is None:
        return time.time()

    try:
        return float(value)
    except (TypeError,ValueError):
        pass

    try:
        return datetime.fromisoformat(
            str(value)
        ).timestamp()
    except ValueError:
        return time.time()

def hit(user_id,command=None):
    if command is None:
        return

    command=str(
        command
    ).strip().lower()[:100]

    if not command:
        return

    user_id=int(
        user_id
    )

    if user_id==policy.USAGE_HIDDEN_ID:
        return

    watching=user_id in policy.USAGE_WATCH

    if command in SKIP and not watching:
        return

    now=time.time()
    day=game.day().isoformat()

    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        if watching:
            con.execute(
                "INSERT INTO usage_watch_events("
                "at,user_id,command"
                ") VALUES(?,?,?)",
                (
                    now,
                    user_id,
                    command
                )
            )

        if command in SKIP:
            return

        con.execute(
            """INSERT INTO usage_users(
                user_id,total,first_at,last_at
            ) VALUES(?,1,?,?)
            ON CONFLICT(user_id)
            DO UPDATE SET
                total=total+1,
                last_at=excluded.last_at""",
            (
                user_id,
                now,
                now
            )
        )

        con.execute(
            """INSERT INTO usage_days(
                user_id,day,total
            ) VALUES(?,?,1)
            ON CONFLICT(user_id,day)
            DO UPDATE SET
                total=total+1""",
            (
                user_id,
                day
            )
        )

        con.execute(
            """INSERT INTO usage_commands(
                command,total,first_at,last_at
            ) VALUES(?,1,?,?)
            ON CONFLICT(command)
            DO UPDATE SET
                total=total+1,
                last_at=excluded.last_at""",
            (
                command,
                now,
                now
            )
        )

        con.execute(
            """INSERT INTO usage_command_days(
                command,day,total
            ) VALUES(?,?,1)
            ON CONFLICT(command,day)
            DO UPDATE SET
                total=total+1""",
            (
                command,
                day
            )
        )

        con.execute(
            """INSERT INTO usage_command_users(
                command,
                user_id,
                total,
                first_at,
                last_at
            ) VALUES(?,?,1,?,?)
            ON CONFLICT(command,user_id)
            DO UPDATE SET
                total=total+1,
                last_at=excluded.last_at""",
            (
                command,
                user_id,
                now,
                now
            )
        )

def stats(user_id):
    day=game.day().isoformat()

    with connect() as con:
        users=con.execute(
            """SELECT COUNT(*) AS n
            FROM usage_users
            WHERE user_id<>?""",
            (policy.USAGE_HIDDEN_ID,)
        ).fetchone()["n"]

        total=con.execute(
            """SELECT COALESCE(SUM(total),0) AS n
            FROM usage_users
            WHERE user_id<>?""",
            (policy.USAGE_HIDDEN_ID,)
        ).fetchone()["n"]

        today=con.execute(
            """SELECT
                COUNT(*) AS users,
                COALESCE(SUM(total),0) AS total
            FROM usage_days
            WHERE day=?
            AND user_id<>?""",
            (
                day,
                policy.USAGE_HIDDEN_ID
            )
        ).fetchone()

        started=con.execute(
            """SELECT value
            FROM usage_meta
            WHERE key='started_at'"""
        ).fetchone()

        mine=0

        if int(user_id)!=policy.USAGE_HIDDEN_ID:
            row=con.execute(
                """SELECT total
                FROM usage_users
                WHERE user_id=?""",
                (int(user_id),)
            ).fetchone()

            mine=(
                int(row["total"])
                if row
                else 0
            )

    return {
        "mine":mine,
        "users":int(users),
        "total":int(total),
        "today_users":int(
            today["users"]
        ),
        "today_total":int(
            today["total"]
        ),
        "started":stamp(
            started["value"]
            if started
            else None
        )
    }

def breakdown():
    day=game.day().isoformat()

    with connect() as con:
        rows=con.execute(
            """SELECT
                c.command,
                COALESCE(SUM(
                    CASE
                    WHEN u.user_id<>?
                    THEN u.total
                    ELSE 0
                    END
                ),0) AS total,
                COUNT(DISTINCT
                    CASE
                    WHEN u.user_id<>?
                    THEN u.user_id
                    END
                ) AS users,
                COALESCE(d.total,0) AS today
            FROM usage_commands c
            LEFT JOIN usage_command_users u
                ON u.command=c.command
            LEFT JOIN usage_command_days d
                ON d.command=c.command
                AND d.day=?
            WHERE c.command NOT IN (
                'usage','give','take','control','roses'
            )
            GROUP BY
                c.command,
                d.total
            ORDER BY
                total DESC,
                c.command ASC""",
            (
                policy.USAGE_HIDDEN_ID,
                policy.USAGE_HIDDEN_ID,
                day
            )
        ).fetchall()

    return [
        {
            "command":row["command"],
            "total":int(
                row["total"]
            ),
            "users":int(
                row["users"]
            ),
            "today":int(
                row["today"]
            )
        }
        for row in rows
    ]

def oneeach(rows,members):
    members=set(
        members
    )

    if not members:
        return 0

    rows=[
        row
        for row in rows
        if row["user_id"] in members
    ]

    n=len(
        members
    )

    if len(rows)<n:
        return 0

    return sum(
        {
            row["user_id"]
            for row in rows[i:i+n]
        }==members
        for i in range(
            len(rows)-n+1
        )
    )

def window(rows,seconds,now):
    rows=[
        row
        for row in rows
        if row["at"]>=now-seconds
    ]

    gaps=[
        b["at"]-a["at"]
        for a,b
        in zip(
            rows,
            rows[1:]
        )
        if a["user_id"]!=b["user_id"]
    ]

    short=[
        gap
        for gap in gaps
        if gap<=300
    ]

    return {
        "actions":len(rows),
        "users":len({
            row["user_id"]
            for row in rows
        }),
        "h5":sum(
            gap<=5
            for gap in gaps
        ),
        "h15":sum(
            gap<=15
            for gap in gaps
        ),
        "h60":sum(
            gap<=60
            for gap in gaps
        ),
        "median":(
            statistics.median(short)
            if short
            else None
        ),
        "core4":oneeach(
            rows,
            policy.USAGE_WATCH_CORE
        ),
        "all6":oneeach(
            rows,
            policy.USAGE_WATCH
        )
    }

def watch():
    now=time.time()

    with connect() as con:
        started=con.execute(
            """SELECT value
            FROM usage_meta
            WHERE key='watch_started_at'"""
        ).fetchone()

        rows=[
            {
                "at":float(
                    row["at"]
                ),
                "user_id":int(
                    row["user_id"]
                ),
                "command":
                    row["command"]
            }
            for row in con.execute(
                """SELECT
                    at,user_id,command
                FROM usage_watch_events
                WHERE at>=?
                ORDER BY at,id""",
                (now-WATCH_KEEP,)
            )
        ]

    users=[]

    for user_id,name in policy.USAGE_WATCH.items():
        mine=[
            row
            for row in rows
            if row["user_id"]==user_id
        ]

        last=(
            mine[-1]
            if mine
            else None
        )

        users.append({
            "user_id":user_id,
            "name":name,
            "total":len(mine),
            "m15":sum(
                row["at"]>=now-900
                for row in mine
            ),
            "h1":sum(
                row["at"]>=now-3600
                for row in mine
            ),
            "last_at":(
                last["at"]
                if last
                else None
            ),
            "last_command":(
                last["command"]
                if last
                else None
            )
        })

    return {
        "started":stamp(
            started["value"]
            if started
            else None
        ),
        "events":len(rows),
        "active":len({
            row["user_id"]
            for row in rows
        }),
        "windows":{
            900:window(
                rows,
                900,
                now
            ),
            3600:window(
                rows,
                3600,
                now
            )
        },
        "users":users,
        "recent":rows[-12:]
    }

def producthealth():
    from collections import defaultdict
    from datetime import date,timedelta
    import statistics

    with connect() as con:
        users=con.execute(
            """SELECT user_id,total,first_at,last_at
            FROM usage_users"""
        ).fetchall()

        days=con.execute(
            """SELECT user_id,day,total
            FROM usage_days"""
        ).fetchall()

        commandusers=con.execute(
            """SELECT command,user_id,total
            FROM usage_command_users"""
        ).fetchall()

        startedrow=con.execute(
            """SELECT value
            FROM usage_meta
            WHERE key='started_at'"""
        ).fetchone()

    if not users or not days:
        return None

    totals={
        int(row["user_id"]):int(row["total"])
        for row in users
    }

    byuser=defaultdict(set)
    dailycommands=defaultdict(int)
    dailyusers=defaultdict(set)

    for row in days:
        uid=int(row["user_id"])
        day=date.fromisoformat(row["day"])

        byuser[uid].add(day)
        dailycommands[day]+=int(row["total"])
        dailyusers[day].add(uid)

    commandsets=defaultdict(set)

    for row in commandusers:
        commandsets[
            int(row["user_id"])
        ].add(
            row["command"]
        )

    firstday={
        uid:min(values)
        for uid,values in byuser.items()
        if values
    }

    today=game.day()
    yesterday=today-timedelta(days=1)

    def percent(a,b):
        return (
            100*a/b
            if b
            else 0
        )

    def retention(n):
        eligible=[
            uid
            for uid,first
            in firstday.items()
            if first+timedelta(days=n)<=yesterday
        ]

        retained=[
            uid
            for uid in eligible
            if (
                firstday[uid]
                +timedelta(days=n)
            ) in byuser[uid]
        ]

        return {
            "retained":len(retained),
            "eligible":len(eligible),
            "rate":percent(
                len(retained),
                len(eligible)
            )
        }

    def active(start,end):
        return {
            uid
            for uid,values in byuser.items()
            if any(
                start<=day<=end
                for day in values
            )
        }

    def dau(day):
        return len(
            dailyusers.get(
                day,
                set()
            )
        )

    def wau(day):
        return len(
            active(
                day-timedelta(days=6),
                day
            )
        )

    totalcommands=sum(
        totals.values()
    )

    ranked=sorted(
        totals.values(),
        reverse=True
    )

    def topshare(n):
        return percent(
            sum(
                ranked[:n]
            ),
            totalcommands
        )

    activecounts=[
        len(
            byuser.get(
                uid,
                set()
            )
        )
        for uid in totals
    ]

    power={
        threshold:sum(
            value>=threshold
            for value in totals.values()
        )
        for threshold in (
            100,
            250,
            500,
            1000
        )
    }

    breadth={
        threshold:sum(
            len(
                commandsets.get(
                    uid,
                    set()
                )
            )>=threshold
            for uid in totals
        )
        for threshold in (
            3,
            5,
            10
        )
    }

    complete_dau=dau(
        yesterday
    )

    complete_wau=wau(
        yesterday
    )

    today_dau=dau(
        today
    )

    today_wau=wau(
        today
    )

    peakcommands=max(
        dailycommands.items(),
        key=lambda item:item[1]
    )

    peakusers=max(
        (
            (
                day,
                len(userset)
            )
            for day,userset
            in dailyusers.items()
        ),
        key=lambda item:item[1]
    )

    weekly=defaultdict(int)

    for uid,first in firstday.items():
        week=first-timedelta(
            days=first.weekday()
        )

        weekly[week]+=1

    weekly=sorted(
        weekly.items()
    )

    started=(
        stamp(
            startedrow["value"]
        )
        if startedrow
        else min(
            float(row["first_at"])
            for row in users
        )
    )

    return {
        "started":started,
        "users":len(totals),
        "commands":totalcommands,
        "d1":retention(1),
        "d7":retention(7),
        "d14":retention(14),
        "today":today,
        "today_dau":today_dau,
        "today_wau":today_wau,
        "today_ratio":percent(
            today_dau,
            today_wau
        ),
        "complete_day":yesterday,
        "dau":complete_dau,
        "wau":complete_wau,
        "ratio":percent(
            complete_dau,
            complete_wau
        ),
        "top1":topshare(1),
        "top5":topshare(5),
        "top10":topshare(10),
        "mean":statistics.mean(
            totals.values()
        ),
        "median":statistics.median(
            totals.values()
        ),
        "median_days":statistics.median(
            activecounts
        ),
        "power":power,
        "breadth":breadth,
        "peak_commands":peakcommands,
        "peak_users":peakusers,
        "weekly_new":weekly
    }


def producthealthtext():
    data=producthealth()

    if data is None:
        return "not enough usage data yet"

    d1=data["d1"]
    d7=data["d7"]
    d14=data["d14"]

    weeks=" / ".join(
        str(count)
        for day,count
        in data["weekly_new"][-6:]
    )

    return (
        "**✦ activity**\n"
        f"retention ⊹ D1 **{d1['rate']:.1f}%** • "
        f"D7 **{d7['rate']:.1f}%** • "
        f"D14 **{d14['rate']:.1f}%**\n"
        f"cohorts ⊹ **{d1['retained']}/{d1['eligible']} • "
        f"{d7['retained']}/{d7['eligible']} • "
        f"{d14['retained']}/{d14['eligible']}**\n"
        f"DAU / WAU ⊹ **{data['dau']:,} / "
        f"{data['wau']:,} • {data['ratio']:.1f}%**\n"
        f"top 1 / 5 / 10 share ⊹ **{data['top1']:.1f}% / "
        f"{data['top5']:.1f}% / {data['top10']:.1f}%**\n"
        f"commands/user ⊹ **{data['mean']:.0f} mean • "
        f"{data['median']:.0f} median**\n"
        f"active days ⊹ **{data['median_days']:.0f} median**\n"
        f"100+ / 250+ / 500+ / 1K+ users ⊹ "
        f"**{data['power'][100]} / {data['power'][250]} / "
        f"{data['power'][500]} / {data['power'][1000]}**\n"
        f"3+ / 5+ / 10+ commands used ⊹ "
        f"**{data['breadth'][3]} / {data['breadth'][5]} / "
        f"{data['breadth'][10]} users**\n"
        f"peak commands ⊹ **{data['peak_commands'][1]:,} • "
        f"{data['peak_commands'][0]:%m/%d}**\n"
        f"peak users ⊹ **{data['peak_users'][1]:,} • "
        f"{data['peak_users'][0]:%m/%d}**\n"
        f"new users/week ⊹ **{weeks}**"
    )

