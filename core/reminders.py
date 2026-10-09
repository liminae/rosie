import importlib
import secrets
import sqlite3
import time

from core import database
from core import game
from core import emoji as rosieemoji

KEYS=("daily","pluck","garden","brew","quests","campaign","pet","marriage","boss","reaper","relic","sin")
DEFAULT={"daily","garden","campaign"}

def connect():
    con=sqlite3.connect(database.FILE,timeout=10)
    con.row_factory=sqlite3.Row
    return con

def init():
    now=time.time()
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS notify_users(
            user_id INTEGER PRIMARY KEY,
            rose INTEGER NOT NULL DEFAULT 1,
            dms INTEGER NOT NULL DEFAULT 1,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS notify_prefs(
            user_id INTEGER NOT NULL,
            key TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id,key)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS notify_seen(
            user_id INTEGER NOT NULL,
            key TEXT NOT NULL,
            scope TEXT NOT NULL DEFAULT '',
            token TEXT NOT NULL,
            seen_at REAL NOT NULL,
            PRIMARY KEY(user_id,key,scope)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS notify_guilds(
            user_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            seen_at REAL NOT NULL,
            PRIMARY KEY(user_id,guild_id)
        )""")
        con.execute(
            "DELETE FROM notify_prefs WHERE key NOT IN ({})".format(
                ",".join("?" for _ in KEYS)
            ),
            KEYS
        )

def register(user_id,guild_id=None):
    now=time.time()
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        found=con.execute(
            "SELECT 1 FROM notify_users WHERE user_id=?",
            (user_id,)
        ).fetchone()
        new=found is None
        if new:
            con.execute(
                "INSERT INTO notify_users(user_id,rose,dms,created_at,updated_at) VALUES(?,1,1,?,?)",
                (user_id,now,now)
            )
        else:
            con.execute(
                "UPDATE notify_users SET updated_at=? WHERE user_id=?",
                (now,user_id)
            )
        for key in KEYS:
            con.execute(
                "INSERT OR IGNORE INTO notify_prefs(user_id,key,enabled) VALUES(?,?,?)",
                (user_id,key,int(key in DEFAULT))
            )
        if guild_id is not None:
            con.execute(
                """INSERT INTO notify_guilds(user_id,guild_id,seen_at)
                VALUES(?,?,?)
                ON CONFLICT(user_id,guild_id)
                DO UPDATE SET seen_at=excluded.seen_at""",
                (user_id,int(guild_id),now)
            )
    return new

def note(user_id,guild_id):
    if guild_id is None:
        return
    with connect() as con:
        con.execute(
            """INSERT INTO notify_guilds(user_id,guild_id,seen_at)
            VALUES(?,?,?)
            ON CONFLICT(user_id,guild_id)
            DO UPDATE SET seen_at=excluded.seen_at""",
            (user_id,int(guild_id),time.time())
        )

def guilds(user_id):
    with connect() as con:
        rows=con.execute(
            "SELECT guild_id FROM notify_guilds WHERE user_id=?",
            (user_id,)
        ).fetchall()
    return {int(row["guild_id"]) for row in rows}

def state(user_id):
    register(user_id)
    with connect() as con:
        user=con.execute(
            "SELECT rose,dms FROM notify_users WHERE user_id=?",
            (user_id,)
        ).fetchone()
        rows=con.execute(
            "SELECT key,enabled FROM notify_prefs WHERE user_id=?",
            (user_id,)
        ).fetchall()
    prefs={key:False for key in KEYS}
    for row in rows:
        if row["key"] in prefs:
            prefs[row["key"]]=bool(row["enabled"])
    return {
        "rose":bool(user["rose"]),
        "dms":bool(user["dms"]),
        "prefs":prefs
    }

def users():
    with connect() as con:
        rows=con.execute(
            "SELECT user_id FROM notify_users "
            "WHERE rose=1 AND dms=1 "
            "ORDER BY user_id"
        ).fetchall()
    return [int(row["user_id"]) for row in rows]

def setrose(user_id,value):
    register(user_id)
    with connect() as con:
        con.execute(
            "UPDATE notify_users "
            "SET rose=?,dms=?,updated_at=? "
            "WHERE user_id=?",
            (int(value),int(value),time.time(),user_id)
        )
    if value:
        primeall(user_id)

def setdms(user_id,value):
    register(user_id)
    with connect() as con:
        con.execute(
            "UPDATE notify_users "
            "SET dms=?,updated_at=? "
            "WHERE user_id=?",
            (int(value),time.time(),user_id)
        )
    if value:
        primeall(user_id)

def toggle(user_id,key):
    if key not in KEYS:
        raise ValueError("bad reminder")
    register(user_id)
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        found=con.execute(
            "SELECT enabled FROM notify_prefs "
            "WHERE user_id=? AND key=?",
            (user_id,key)
        ).fetchone()
        value=not bool(found["enabled"] if found else 0)
        con.execute(
            """INSERT INTO notify_prefs(user_id,key,enabled)
            VALUES(?,?,?)
            ON CONFLICT(user_id,key)
            DO UPDATE SET enabled=excluded.enabled""",
            (user_id,key,int(value))
        )
    if value:
        prime(user_id,key)
    return value

def rows(path,sql,args=()):
    try:
        con=sqlite3.connect(path,timeout=5)
        con.row_factory=sqlite3.Row
        try:
            return [
                dict(row)
                for row in con.execute(sql,args).fetchall()
            ]
        finally:
            con.close()
    except sqlite3.Error:
        return []

def one(path,sql,args=()):
    found=rows(path,sql,args)
    return found[0] if found else None

def atom(key,scope,token,**extra):
    data={
        "key":key,
        "scope":str(scope),
        "token":str(token)
    }
    data.update(extra)
    return data

def current(user_id,key,now=None):
    now=now or time.time()
    today=game.day().isoformat()

    if key=="daily":
        row=one(
            game.DB,
            "SELECT daily_last FROM users WHERE user_id=?",
            (user_id,)
        )
        return (
            [atom(key,"",today)]
            if row is None or row["daily_last"]!=today
            else []
        )

    if key=="pluck":
        row=one(
            database.FILE,
            "SELECT last_pluck,disease "
            "FROM pluck_users WHERE user_id=?",
            (user_id,)
        )
        if row is None or not row["last_pluck"]:
            return []
        day=one(
            database.FILE,
            "SELECT count FROM pluck_days "
            "WHERE user_id=? AND day=?",
            (user_id,today)
        )
        if day and int(day["count"] or 0)>=50:
            return []
        cooldown=900 if row["disease"]=="roseola" else 600
        if now>=float(row["last_pluck"])+cooldown:
            return [
                atom(
                    key,
                    "",
                    f"{float(row['last_pluck']):.6f}"
                )
            ]
        return []

    if key=="garden":
        found=rows(
            game.DB,
            "SELECT plot,ready_at "
            "FROM garden_v2_plants "
            "WHERE user_id=? AND ready_at<=? "
            "ORDER BY plot",
            (user_id,now)
        )
        return [
            atom(
                key,
                row["plot"],
                f"{float(row['ready_at']):.6f}"
            )
            for row in found
        ]

    if key=="brew":
        row=one(
            database.FILE,
            "SELECT rose_finished_at,gxp_finished_at "
            "FROM brew_users WHERE user_id=?",
            (user_id,)
        )

        if row is None:
            return []

        out=[]

        for scope,column,name in (
            (
                "rose_tonic",
                "rose_finished_at",
                "rose tonic"
            ),
            (
                "knowledge",
                "gxp_finished_at",
                "knowledge"
            )
        ):
            if row.get(
                column
            ):
                out.append(
                    atom(
                        key,
                        scope,
                        f"{float(row[column]):.6f}",
                        name=name
                    )
                )

        return out

    if key=="quests":
        row=one(
            database.FILE,
            "SELECT 1 AS yes FROM quest_days "
            "WHERE user_id=? AND day=?",
            (user_id,today)
        )
        return [] if row else [atom(key,"",today)]

    if key=="campaign":
        row=one(
            database.FILE,
            "SELECT id,active,started_at "
            "FROM campaign_runs "
            "WHERE user_id=? "
            "ORDER BY id DESC LIMIT 1",
            (user_id,)
        )
        if (
            row
            and not row["active"]
            and now>=float(row["started_at"])+900
        ):
            return [atom(key,"",row["id"])]
        return []

    if key=="pet":
        petmod=importlib.import_module(
            "commands.pet"
        )

        with petmod.connect() as con:
            pet=petmod.active(
                con,
                user_id,
                now
            )

        if pet is None:
            return []

        out=[]

        if now>=float(pet["last_feed"])+petmod.FEED_CD:
            out.append(
                atom(
                    key,
                    "feed",
                    f"{float(pet['last_feed']):.6f}",
                    action="feed"
                )
            )

        if (
            pet["energy"]>=10
            and now>=float(pet["last_play"])+petmod.PLAY_CD
        ):
            out.append(
                atom(
                    key,
                    "play",
                    f"{float(pet['last_play']):.6f}",
                    action="play"
                )
            )

        if (
            pet["energy"]>=15
            and now>=float(pet["last_explore"])+petmod.EXPLORE_CD
        ):
            out.append(
                atom(
                    key,
                    "explore",
                    f"{float(pet['last_explore']):.6f}",
                    action="explore"
                )
            )

        return out

    if key=="marriage":
        row=one(
            database.FILE,
            """SELECT id,last_claim FROM marriages
            WHERE ended_at IS NULL
            AND (user1_id=? OR user2_id=?)
            ORDER BY id DESC LIMIT 1""",
            (user_id,user_id)
        )
        if (
            row
            and now>=float(row["last_claim"])+604800
        ):
            return [
                atom(
                    key,
                    "",
                    f"{row['id']}:{float(row['last_claim']):.6f}"
                )
            ]
        return []

    known=guilds(user_id)

    if not known:
        return []

    db=database.FILE
    sql=None

    if key=="boss":
        sql=(
            "SELECT id,guild_id,channel_id "
            "FROM boss_games "
            "WHERE active=1 "
            "ORDER BY id"
        )

    elif key=="reaper":
        db=game.DB
        sql=(
            "SELECT id,guild_id,channel_id "
            "FROM reaper_games "
            "WHERE active=1 "
            "AND COALESCE(testing,0)=0 "
            "ORDER BY id"
        )

    elif key=="relic":
        sql=(
            "SELECT id,guild_id,channel_id "
            "FROM relic_games "
            "WHERE active=1 "
            "ORDER BY id"
        )

    if sql:
        return [
            atom(
                key,
                row["guild_id"],
                row["id"],
                guild_id=int(row["guild_id"]),
                channel_id=int(row["channel_id"])
            )
            for row in rows(db,sql)
            if int(row["guild_id"]) in known
        ]

    if key=="sin":
        out=[]

        for row in rows(
            game.DB,
            "SELECT id,guild_id,channel_id,current_day "
            "FROM sin_games "
            "WHERE active=1 "
            "AND COALESCE(testing,0)=0 "
            "ORDER BY id"
        ):
            guild_id=int(row["guild_id"])

            if guild_id not in known:
                continue

            chosen=one(
                game.DB,
                "SELECT 1 AS yes "
                "FROM sin_choices "
                "WHERE game_id=? "
                "AND day=? "
                "AND user_id=?",
                (
                    row["id"],
                    row["current_day"],
                    user_id
                )
            )

            if chosen is None:
                out.append(
                    atom(
                        key,
                        guild_id,
                        f"{row['id']}:{row['current_day']}",
                        guild_id=guild_id,
                        channel_id=int(row["channel_id"])
                    )
                )

        return out

    return []

def seen(user_id):
    with connect() as con:
        rows=con.execute(
            "SELECT key,scope,token "
            "FROM notify_seen "
            "WHERE user_id=?",
            (user_id,)
        ).fetchall()

    return {
        (row["key"],row["scope"]):row["token"]
        for row in rows
    }

def prefs(user_id):
    data=state(user_id)
    return {
        key
        for key,value in data["prefs"].items()
        if value
    },data

def due(user_id):
    enabled,data=prefs(user_id)

    if not data["rose"] or not data["dms"]:
        return []

    old=seen(user_id)
    out=[]

    for key in KEYS:
        if key not in enabled:
            continue

        atoms=current(user_id,key)

        fresh=[
            item
            for item in atoms
            if old.get(
                (key,item["scope"])
            )!=item["token"]
        ]

        if not fresh:
            continue

        if key in (
            "boss",
            "reaper",
            "relic",
            "sin"
        ):
            groups={}

            for item in atoms:
                groups.setdefault(
                    item.get("guild_id"),
                    []
                ).append(item)

            for guild_id in {
                item.get("guild_id")
                for item in fresh
            }:
                group=groups[guild_id]

                out.append({
                    "key":key,
                    "guild_id":guild_id,
                    "channel_id":group[0].get(
                        "channel_id"
                    ),
                    "marks":[
                        (
                            item["scope"],
                            item["token"]
                        )
                        for item in group
                    ]
                })

            continue

        event={
            "key":key,
            "marks":[
                (
                    item["scope"],
                    item["token"]
                )
                for item in atoms
            ]
        }

        if key=="garden":
            event["count"]=len(atoms)

        if key=="pet":
            event["actions"]=[
                item["action"]
                for item in atoms
            ]

        if key=="brew":
            event["brews"]=[
                item["name"]
                for item in fresh
            ]

        out.append(event)

    return out

def mark(user_id,event):
    now=time.time()

    with connect() as con:
        con.execute("BEGIN IMMEDIATE")

        for scope,token in event["marks"]:
            con.execute(
                """INSERT INTO notify_seen(
                    user_id,key,scope,token,seen_at
                ) VALUES(?,?,?,?,?)
                ON CONFLICT(user_id,key,scope)
                DO UPDATE SET
                token=excluded.token,
                seen_at=excluded.seen_at""",
                (
                    user_id,
                    event["key"],
                    str(scope),
                    str(token),
                    now
                )
            )

def prime(user_id,key):
    atoms=current(user_id,key)

    if atoms:
        mark(
            user_id,
            {
                "key":key,
                "marks":[
                    (
                        item["scope"],
                        item["token"]
                    )
                    for item in atoms
                ]
            }
        )

def primeall(user_id):
    enabled,_=prefs(user_id)

    for key in enabled:
        prime(user_id,key)

def message(name,event,guild=None):
    key=event["key"]
    server=guild or "one of ur servers"

    if key=="garden":
        count=int(
            event.get("count",1)
        )
        thing="crop" if count==1 else "crops"
        verb="is" if count==1 else "are"

        return secrets.choice((
            f"psst {name} 🌱\n"
            f"{count} {thing} in ur garden {verb} ready. go harvest",

            f"hallo {name} 🌱\n"
            f"ur garden has {count} ready {thing}. theyre getting impatient",

            f"oi {name} 🌱\n"
            f"{count} {thing} ready in /garden. i am not watering them for you"
        ))

    if key=="pet":
        actions=event.get(
            "actions"
        ) or []

        text=" / ".join(actions)

        return secrets.choice((
            f"{name} ur creature is bothering me 🐾\n"
            f"{text} "
            f"{'is' if len(actions)==1 else 'are'} ready again",

            f"hallo {name} 🐾\n"
            f"ur pet has demands. ready ⊹ {text}",

            f"oi {name} 🐾\n"
            f"pet stuff is ready again ⊹ {text}"
        ))

    if key=="brew":
        brews=event.get(
            "brews"
        ) or ["brew"]

        label=" + ".join(
            brews
        )

        return secrets.choice((
            f"oi {name} 🧪\n"
            f"ur {label} ran out of charges. /brew if u want another",

            f"hallo {name} 🧪\n"
            f"{label} is empty. potion privileges revoked",

            f"{name} babe 🧪\n"
            f"last {label} charge is gone"
        ))

    pools={
        "daily":(
            f'hallo {name} {rosieemoji.ROSE}\nur daily is back. come collect ur government assistance',

            f'oi {name} {rosieemoji.ROSE}\n/daily is ready again. free money department is open',

            f'{name} babe {rosieemoji.ROSE}\nrosie remembered ur daily even if u didnt'
        ),

        "pluck":(
            f'psst {name} {rosieemoji.ROSE}\nthe bush has forgiven you. /pluck is ready again',

            f'oi {name} {rosieemoji.ROSE}\nur hands are legally allowed near the roses again',

            f'hallo {name} {rosieemoji.ROSE}\n/pluck is ready. go bother the bush'
        ),

        "quests":(
            f"hallo {name} 📜\n"
            "new quests dropped. rosie has assigned chores",

            f"{name} babe 📜\n"
            "new /quests. employment is unfortunately mandatory",

            f"oi {name} 📜\n"
            "todays quests are waiting to judge you"
        ),

        "campaign":(
            f'hallo {name} {rosieemoji.ROSE}\n/campaign is ready again. pick ur poison',

            f'oi {name} {rosieemoji.ROSE}\n/campaign is ready. bad decisions have reopened',

            f'{name} babe {rosieemoji.ROSE}\nur next /campaign is ready'
        ),

        "marriage":(
            "hallo lovergirl 💍\n"
            "ur marriage stipend is ready. capitalism survives another week",

            f"oi {name} 💍\n"
            "marriage money is ready. romance has payroll now",

            f"{name} 💍\n"
            "ur weekly marriage stipend is waiting"
        ),

        "boss":(
            f"WAKE UP {name} 🩸\n"
            f"a mimic spawned in {server}",

            f"oi {name} 🩸\n"
            f"{server} has a mimic problem. go make it worse",

            f"{name} babe 🩸\n"
            f"boss fight in {server}. violence is currently encouraged"
        ),

        "reaper":(
            f"oi {name} 💀\n"
            f"reaper started in {server}. go be annoying",

            f"{name} 💀\n"
            f"the clock is ticking in {server}. reap somebody's patience",

            f"WAKE UP {name} 💀\n"
            f"reaper is live in {server}"
        ),

        "relic":(
            f"pspsps {name} 🥀\n"
            f"a relic started in {server}. stealing is encouraged",

            f"oi {name} 🥀\n"
            f"relic is live in {server}. theft has been temporarily legalized",

            f"{name} babe 🥀\n"
            f"somebody put a relic in {server}. take it personally"
        ),

        "sin":(
            "hallo sinner ♦️\n"
            f"new sin day in {server}. pick ur number before midnight",

            f"oi {name} ♦️\n"
            f"{server} needs ur sin number for today",

            f"{name} ♦️\n"
            f"new sin day in {server}. be greedy responsibly"
        )
    }

    return secrets.choice(
        pools[key]
    )
