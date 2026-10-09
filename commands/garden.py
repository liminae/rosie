import asyncio
import json
import secrets
import sqlite3
import time

import discord
from core import database
from core import game
from core import brewing
from core import petcatalog
from discord import app_commands
from discord.ext import commands
from core import emoji as rosieemoji

CAP=1250
MAX_CAP=3000
CAP_PER_LEVEL=50
BOUQUET=100
PLOT_REQ={4:(5,5000),5:(15,20000)}
ORDER=("rosebud","tulip","daisy","rose","cherry_blossom","hyacinth","lily","hibiscus","sunflower","white_flower","lotus","rosette","wilted","moonflower")
PLANTS={
    "rosebud":{"name":"rosebud","emoji":"🌱","seconds":900,"cost":100,"profit":20,"xp":7,"level":1},
    "tulip":{"name":"tulip","emoji":"🌷","seconds":1800,"cost":200,"profit":35,"xp":15,"level":1},
    "daisy":{"name":"daisy","emoji":"🌼","seconds":3600,"cost":300,"profit":60,"xp":30,"level":1},
    "rose":{"name":"rose","emoji":rosieemoji.ROSE,"seconds":7200,"cost":450,"profit":100,"xp":65,"level":3},
    "cherry_blossom":{"name":"cherry blossom","emoji":"🌸","seconds":10800,"cost":650,"profit":135,"xp":100,"level":5},
    "hyacinth":{"name":"hyacinth","emoji":"🪻","seconds":14400,"cost":800,"profit":160,"xp":140,"level":7},
    "lily":{"name":"lily","emoji":"⚜️","seconds":18000,"cost":900,"profit":170,"xp":160,"level":8},
    "hibiscus":{"name":"hibiscus","emoji":"🌺","seconds":18000,"cost":1000,"profit":180,"xp":180,"level":10},
    "sunflower":{"name":"sunflower","emoji":"🌻","seconds":21600,"cost":1250,"profit":200,"xp":220,"level":12},
    "white_flower":{"name":"white flower","emoji":"💮","seconds":28800,"cost":1500,"profit":240,"xp":300,"level":15},
    "lotus":{"name":"lotus","emoji":"🪷","seconds":36000,"cost":1750,"profit":270,"xp":390,"level":20},
    "rosette":{"name":"rosette","emoji":"🏵️","seconds":43200,"cost":2000,"profit":300,"xp":480,"level":25},
    "wilted":{"name":"wilted flower","emoji":"🥀","seconds":57600,"cost":2500,"profit":325,"xp":650,"level":30},
    "moonflower":{"name":"moonflower","emoji":"🌙","seconds":64800,"cost":3000,"profit":450,"xp":850,"level":40}
}
LEGACY={"rosebud":(100,600),"tulip":(250,1800),"lily":(500,7200),"moonflower":(1000,21600)}
LOCKS={}

# Ordinary high-level garden event chance, per harvested plant.
# Values are basis points out of 10,000.
GARDEN_EVENT_RATES=(
    (1000,125),
    (500,100),
    (250,75),
    (50,50)
)

GARDEN_EVENTS=(
    {
        "key":"dewfall",
        "level":50,
        "emoji":"💧",
        "label":"dewfall",
        "text":"one bead of dew stayed after the rest evaporated.",
        "ingredients":{"dew":1}
    },
    {
        "key":"petal_drift",
        "level":50,
        "emoji":rosieemoji.ROSE,
        "label":"petal drift",
        "text":"a little spiral of petals settled between the plots.",
        "ingredients":{"petal":2}
    },
    {
        "key":"herb_sprig",
        "level":250,
        "emoji":"🌿",
        "label":"wild sprig",
        "text":"something useful grew where you definitely did not plant it.",
        "ingredients":{"herb":2}
    },
    {
        "key":"silver_bloom",
        "level":250,
        "emoji":"✨",
        "label":"silver bloom",
        "text":"one flower flashed silver before returning to normal.",
        "gxp":100
    },
    {
        "key":"moon_dew",
        "level":500,
        "emoji":"🌙",
        "label":"moon dew",
        "text":"cold dew collected under the leaves without any rain.",
        "ingredients":{"dew":2}
    },
    {
        "key":"wild_growth",
        "level":500,
        "emoji":"🌱",
        "label":"wild growth",
        "text":"the soil shifted and every stem stood a little taller.",
        "gxp":250
    },
    {
        "key":"rosarium_bloom",
        "level":1000,
        "emoji":rosieemoji.ROSE,
        "label":"rosarium bloom",
        "text":"for a moment, the whole garden bloomed at once.",
        "gxp":500
    },
    {
        "key":"impossible_bouquet",
        "level":1000,
        "emoji":"💐",
        "label":"impossible bouquet",
        "text":"a bouquet appeared where there was bare soil a second ago.",
        "ingredients":{
            "petal":3,
            "herb":2,
            "dew":1
        }
    }
)

def connect(econ=False):
    con=sqlite3.connect(game.DB,timeout=10)
    con.row_factory=sqlite3.Row
    if econ:
        con.execute("ATTACH DATABASE ? AS econ",(database.FILE,))
    return con

def tables(con):
    return {row["name"] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}

def cols(con,name):
    return {row["name"] for row in con.execute(f"PRAGMA table_info({name})")}

def init():
    brewing.init()

    with sqlite3.connect(
        database.FILE
    ) as econ:
        econ.execute(
            """CREATE TABLE IF NOT EXISTS pet_rosarium(
                user_id INTEGER PRIMARY KEY,
                butterfly_encountered_at REAL,
                butterfly_adopted_at REAL
            )"""
        )

    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS garden_v2_users(
            user_id INTEGER PRIMARY KEY,
            xp INTEGER NOT NULL DEFAULT 0,
            plots INTEGER NOT NULL DEFAULT 3
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS garden_v2_plants(
            user_id INTEGER NOT NULL,
            guild_id INTEGER,
            plot INTEGER NOT NULL,
            plant TEXT NOT NULL,
            planted_at REAL NOT NULL,
            ready_at REAL NOT NULL,
            deposit INTEGER NOT NULL,
            PRIMARY KEY(user_id,plot)
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS garden_v2_daily(
            user_id INTEGER NOT NULL,
            day TEXT NOT NULL,
            profit INTEGER NOT NULL DEFAULT 0,
            bouquet INTEGER NOT NULL DEFAULT 0,
            varieties TEXT NOT NULL DEFAULT '[]',
            planted INTEGER NOT NULL DEFAULT 0,
            harvested INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id,day)
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS garden_v2_meta(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS garden_v2_collection(
            user_id INTEGER NOT NULL,
            plant TEXT NOT NULL,
            found_at REAL NOT NULL,
            PRIMARY KEY(user_id,plant)
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS garden_v2_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            event TEXT NOT NULL,
            level INTEGER NOT NULL,
            plot INTEGER,
            reward TEXT NOT NULL DEFAULT '{}',
            occurred_at REAL NOT NULL
        )""")

        plantcols={
            row["name"]
            for row in con.execute(
                "PRAGMA table_info(garden_v2_plants)"
            )
        }

        if "guild_id" not in plantcols:
            con.execute(
                """ALTER TABLE garden_v2_plants
                ADD COLUMN guild_id INTEGER"""
            )

    migrate()
    backfill_collection()

def migrateguild(guild_id):
    with connect() as con:
        con.execute("UPDATE garden_v2_plants SET guild_id=? WHERE guild_id IS NULL",(guild_id,))

def migrate():
    def pick(c,names):
        return next((x for x in names if x in c),None)

    def plantkey(value):
        text=str(value or "").strip().lower()
        emoji={
            "🌱":"rosebud",
            "🌷":"tulip",
            "🌼":"daisy",
            rosieemoji.ROSE:"rose",
            "🌸":"cherry_blossom",
            "🪻":"hyacinth",
            "⚜️":"lily",
            "⚜":"lily",
            "🌺":"hibiscus",
            "🌻":"sunflower",
            "💮":"white_flower",
            "🪷":"lotus",
            "🏵️":"rosette",
            "🏵":"rosette",
            "🥀":"wilted",
            "🌙":"moonflower"
        }
        for mark,key in emoji.items():
            if mark in text:
                return key
        clean="".join(ch if ch.isalnum() else "_" for ch in text).strip("_")
        while "__" in clean:
            clean=clean.replace("__","_")
        aliases={
            "0":"rosebud",
            "1":"tulip",
            "2":"lily",
            "3":"moonflower",
            "rose_bud":"rosebud",
            "cherryblossom":"cherry_blossom",
            "whiteflower":"white_flower",
            "wilted_flower":"wilted",
            "moon_flower":"moonflower"
        }
        clean=aliases.get(clean,clean)
        if clean in PLANTS:
            return clean
        for key,data in PLANTS.items():
            names=(key,data["name"].replace(" ","_"))
            if any(name and name in clean for name in names):
                return key
        return None

    with connect() as con:
        oldtables=tables(con)
        rescued=0
        profiles=0

        if "garden_users" in oldtables:
            c=cols(con,"garden_users")
            uid=pick(c,("user_id","user","id"))
            xpcol=pick(c,("xp","experience"))
            plotscol=pick(c,("plots","plot_count","slots"))

            if uid:
                for row in con.execute("SELECT * FROM garden_users"):
                    user_id=int(row[uid])
                    oldxp=int(row[xpcol] or 0) if xpcol else 0
                    oldplots=int(row[plotscol] or 3) if plotscol else 3
                    current=con.execute(
                        "SELECT xp,plots FROM garden_v2_users WHERE user_id=?",
                        (user_id,)
                    ).fetchone()

                    if current is None:
                        con.execute(
                            "INSERT INTO garden_v2_users(user_id,xp,plots) VALUES(?,?,?)",
                            (user_id,oldxp,max(3,oldplots))
                        )
                        profiles+=1
                    else:
                        xp=max(int(current["xp"]),oldxp)
                        plots=max(int(current["plots"]),oldplots)
                        if xp!=current["xp"] or plots!=current["plots"]:
                            con.execute(
                                "UPDATE garden_v2_users SET xp=?,plots=? WHERE user_id=?",
                                (xp,plots,user_id)
                            )
                            profiles+=1

        for table in sorted(oldtables):
            if table=="garden_v2_plants":
                continue
            if "garden" not in table.lower():
                continue

            c=cols(con,table)
            uid=pick(c,("user_id","user","member_id","discord_id"))
            plotcol=pick(c,("plot","plot_id","slot","slot_id","position"))
            plantcol=pick(c,("plant","crop","kind","type","plant_key","name"))

            if not uid or not plotcol or not plantcol:
                continue

            plantedcol=pick(c,("planted_at","planted","started_at","created_at","plant_time"))
            readycol=pick(c,("ready_at","harvest_at","finishes_at","ends_at","ready"))
            depositcol=pick(c,("deposit","cost","price"))

            for row in con.execute(f"SELECT * FROM {table}"):
                try:
                    user_id=int(row[uid])
                    plot=int(row[plotcol])
                    key=plantkey(row[plantcol])
                except Exception:
                    continue

                if key not in PLANTS or plot<1 or plot>5:
                    continue

                exists=con.execute(
                    "SELECT 1 FROM garden_v2_plants WHERE user_id=? AND plot=?",
                    (user_id,plot)
                ).fetchone()

                if exists:
                    continue

                cfg=PLANTS[key]
                oldcost,oldseconds=LEGACY.get(key,(cfg["cost"],cfg["seconds"]))

                try:
                    planted=float(row[plantedcol]) if plantedcol and row[plantedcol] is not None else None
                except Exception:
                    planted=None

                try:
                    ready=float(row[readycol]) if readycol and row[readycol] is not None else None
                except Exception:
                    ready=None

                if ready is None:
                    if planted is None:
                        planted=time.time()
                    ready=planted+oldseconds

                if planted is None:
                    planted=ready-oldseconds

                try:
                    deposit=int(row[depositcol]) if depositcol and row[depositcol] is not None else oldcost
                except Exception:
                    deposit=oldcost

                before=con.total_changes

                con.execute(
                    "INSERT OR IGNORE INTO garden_v2_users(user_id) VALUES(?)",
                    (user_id,)
                )
                con.execute(
                    """INSERT OR IGNORE INTO garden_v2_plants(
                        user_id,plot,plant,planted_at,ready_at,deposit
                    ) VALUES(?,?,?,?,?,?)""",
                    (user_id,plot,key,planted,ready,deposit)
                )

                if con.total_changes>before:
                    rescued+=1

        con.execute(
            "INSERT OR REPLACE INTO garden_v2_meta(key,value) VALUES('garden_v2_rescue','1')"
        )

        print(
            f"garden rescue ⊹ {rescued} old flower row(s) checked/restored "
            f"⊹ {profiles} profile(s) merged"
        )

def lvl(xp):
    return 1+int(xp)//250


def garden_event_rate(
    level
):
    for minimum,basis_points in GARDEN_EVENT_RATES:
        if level>=minimum:
            return basis_points

    return 0


def garden_event_reward(
    event
):
    if event.get(
        "gxp"
    ):
        return (
            f"+{int(event['gxp']):,} GXP"
        )

    parts=[]

    for key,amount in event.get(
        "ingredients",
        {}
    ).items():
        cfg=brewing.INGREDIENTS[
            key
        ]

        name=(
            cfg[
                "name"
            ]
            if amount==1
            else cfg[
                "plural"
            ]
        )

        parts.append(
            f"+{amount} {name} "
            f"{cfg['emoji']}"
        )

    return " • ".join(
        parts
    )


def roll_garden_event(
    level,
    plots
):
    rate=garden_event_rate(
        level
    )

    if not rate:
        return None

    eligible=[
        event
        for event in GARDEN_EVENTS
        if level>=event[
            "level"
        ]
    ]

    if not eligible:
        return None

    for plot in plots:
        if secrets.randbelow(
            10000
        )<rate:
            event=dict(
                secrets.choice(
                    eligible
                )
            )

            event[
                "plot"
            ]=plot

            return event

    return None


def apply_garden_event(
    con,
    user_id,
    event
):
    gxp=int(
        event.get(
            "gxp",
            0
        )
    )

    ingredients=event.get(
        "ingredients",
        {}
    )

    if ingredients:
        con.execute(
            """INSERT OR IGNORE INTO econ.brew_users(
                user_id
            ) VALUES(?)""",
            (
                user_id,
            )
        )

        for key,amount in ingredients.items():
            if key not in brewing.INGREDIENTS:
                continue

            con.execute(
                f"""UPDATE econ.brew_users
                SET {key}={key}+?
                WHERE user_id=?""",
                (
                    int(
                        amount
                    ),
                    user_id
                )
            )

    return gxp


def record_garden_event(
    con,
    user_id,
    key,
    level,
    plot,
    reward,
    now
):
    con.execute(
        """INSERT INTO garden_v2_events(
            user_id,
            event,
            level,
            plot,
            reward,
            occurred_at
        ) VALUES(?,?,?,?,?,?)""",
        (
            user_id,
            key,
            level,
            plot,
            json.dumps(
                reward,
                sort_keys=True
            ),
            now
        )
    )


def butterfly_eligible(
    con,
    user_id,
    level
):
    if level<petcatalog.ROSARIUM_GARDEN_LEVEL:
        return False

    econ_tables={
        row["name"]
        for row in con.execute(
            """SELECT name
            FROM econ.sqlite_master
            WHERE type='table'"""
        )
    }

    if not {
        "pets",
        "pet_rosarium"
    }<=econ_tables:
        return False

    status=con.execute(
        """SELECT butterfly_encountered_at
        FROM econ.pet_rosarium
        WHERE user_id=?""",
        (
            user_id,
        )
    ).fetchone()

    if (
        status
        and status[
            "butterfly_encountered_at"
        ]
    ):
        return False

    already=con.execute(
        """SELECT 1
        FROM econ.pets
        WHERE user_id=?
        AND species='butterfly'""",
        (
            user_id,
        )
    ).fetchone()

    if already:
        return False

    marks=",".join(
        "?"
        for _ in petcatalog.NORMAL_SPECIES
    )

    owned=con.execute(
        f"""SELECT COUNT(DISTINCT species)
        FROM econ.pets
        WHERE user_id=?
        AND species IN ({marks})""",
        (
            user_id,
            *petcatalog.NORMAL_SPECIES
        )
    ).fetchone()[0]

    return (
        int(
            owned
        )>=petcatalog.ROSARIUM_NORMALS
    )


def roll_butterfly(
    con,
    user_id,
    level,
    plots,
    now
):
    if not butterfly_eligible(
        con,
        user_id,
        level
    ):
        return None

    for plot in plots:
        if secrets.randbelow(
            10000
        )<petcatalog.ROSARIUM_BUTTERFLY_BP:
            con.execute(
                """INSERT INTO econ.pet_rosarium(
                    user_id,
                    butterfly_encountered_at
                ) VALUES(?,?)
                ON CONFLICT(user_id)
                DO UPDATE SET
                    butterfly_encountered_at=
                    COALESCE(
                        pet_rosarium.butterfly_encountered_at,
                        excluded.butterfly_encountered_at
                    )""",
                (
                    user_id,
                    now
                )
            )

            return plot

    return None


def cap(xp):
    return min(MAX_CAP,CAP+CAP_PER_LEVEL*(lvl(xp)-1))

def duration(seconds):
    if seconds%3600==0:
        return f"{seconds//3600}h"
    return f"{seconds//60}m"

def touch_con(con,user_id):
    con.execute(
        "INSERT OR IGNORE INTO garden_v2_users(user_id) VALUES(?)",
        (user_id,)
    )
    con.execute(
        "INSERT OR IGNORE INTO garden_v2_daily(user_id,day) VALUES(?,?)",
        (user_id,game.day().isoformat())
    )

def daily_con(con,user_id):
    touch_con(con,user_id)
    row=con.execute(
        "SELECT * FROM garden_v2_daily WHERE user_id=? AND day=?",
        (user_id,game.day().isoformat())
    ).fetchone()
    data=dict(row)
    try:
        data["varieties"]=json.loads(data["varieties"])
    except Exception:
        data["varieties"]=[]
    return data

def legacy_bump(con,user_id,kind,amount):
    if "garden_daily" not in tables(con):
        return
    c=cols(con,"garden_daily")
    if not {"user_id","day"}<=c:
        return
    try:
        con.execute(
            "INSERT OR IGNORE INTO garden_daily(user_id,day) VALUES(?,?)",
            (user_id,game.day().isoformat())
        )
    except sqlite3.Error:
        return
    choices=("plants","planted","plant_count") if kind=="plant" else ("harvests","harvested","harvest_count")
    for name in choices:
        if name in c:
            con.execute(
                f"UPDATE garden_daily SET {name}=COALESCE({name},0)+? WHERE user_id=? AND day=?",
                (amount,user_id,game.day().isoformat())
            )

def legacy_user(con,user_id,xp,plots):
    if "garden_users" not in tables(con):
        return
    c=cols(con,"garden_users")
    if "user_id" not in c:
        return
    try:
        con.execute(
            "INSERT OR IGNORE INTO garden_users(user_id) VALUES(?)",
            (user_id,)
        )
    except sqlite3.Error:
        pass

    sets=[]
    values=[]

    if "xp" in c:
        sets.append("xp=?")
        values.append(xp)

    if "plots" in c:
        sets.append("plots=?")
        values.append(plots)

    if sets:
        try:
            con.execute(
                f"UPDATE garden_users SET {','.join(sets)} WHERE user_id=?",
                (*values,user_id)
            )
        except sqlite3.Error:
            pass

def legacy_plant(con,user_id,plot,key,planted_at):
    if "garden_plants" not in tables(con):
        return
    c=cols(con,"garden_plants")
    if not {"user_id","plot","plant","planted_at"}<=c:
        return
    try:
        con.execute(
            "DELETE FROM garden_plants WHERE user_id=? AND plot=?",
            (user_id,plot)
        )
        con.execute(
            "INSERT INTO garden_plants(user_id,plot,plant,planted_at) VALUES(?,?,?,?)",
            (user_id,plot,key,planted_at)
        )
    except sqlite3.Error:
        pass

def legacy_delete(con,user_id,plots):
    if not plots or "garden_plants" not in tables(con):
        return
    c=cols(con,"garden_plants")
    if not {"user_id","plot"}<=c:
        return
    try:
        con.executemany(
            "DELETE FROM garden_plants WHERE user_id=? AND plot=?",
            [(user_id,plot) for plot in plots]
        )
    except sqlite3.Error:
        pass

def backfill_collection():
    now=time.time()
    with connect() as con:
        rows=con.execute(
            "SELECT user_id,varieties FROM garden_v2_daily"
        ).fetchall()

        added=0

        for row in rows:
            try:
                found=json.loads(row["varieties"] or "[]")
            except Exception:
                found=[]

            for key in found:
                if key not in PLANTS:
                    continue

                cur=con.execute(
                    """INSERT OR IGNORE INTO garden_v2_collection(
                        user_id,plant,found_at
                    ) VALUES(?,?,?)""",
                    (row["user_id"],key,now)
                )

                added+=cur.rowcount

    if added:
        print(
            f"garden collection ⊹ "
            f"{added} historical first harvest(s) backfilled"
        )

def collection(user_id,con=None):
    own=con is None
    db=connect() if own else con

    try:
        rows=db.execute(
            """SELECT plant
            FROM garden_v2_collection
            WHERE user_id=?
            ORDER BY found_at,plant""",
            (user_id,)
        ).fetchall()

        return {
            row["plant"]
            for row in rows
            if row["plant"] in PLANTS
        }

    finally:
        if own:
            db.close()

def allknowing(user_id,con=None):
    own=con is None
    db=connect() if own else con

    try:
        touch_con(db,user_id)

        row=db.execute(
            "SELECT xp FROM garden_v2_users WHERE user_id=?",
            (user_id,)
        ).fetchone()

        return bool(
            row
            and lvl(row["xp"])>=40
            and len(collection(user_id,db))>=len(ORDER)
        )

    finally:
        if own:
            db.close()

def collection_embed(user_id):
    with connect() as con:
        touch_con(con,user_id)

        row=con.execute(
            "SELECT xp FROM garden_v2_users WHERE user_id=?",
            (user_id,)
        ).fetchone()

        level=lvl(row["xp"])
        got=collection(user_id,con)

    if level>=40 and len(got)>=len(ORDER):
        return discord.Embed(
            title=rosieemoji.ROSE + ' the all-knowing rose',
            description=(
                f"collection ⊹ **{len(got)}/{len(ORDER)}**\n"
                "blocked bloom ⊹ **GXP 1:1**\n"
                "unlocked ✦"
            ),
            color=discord.Color.dark_red()
        )

    return discord.Embed(
        title="❔ ???",
        description=(
            f"collection ⊹ **{len(got)}/{len(ORDER)}**\n"
            f"level ⊹ **{min(level,40)}/40**"
        ),
        color=discord.Color.dark_red()
    )

def state(user_id):
    with connect() as con:
        touch_con(con,user_id)
        u=dict(
            con.execute(
                "SELECT * FROM garden_v2_users WHERE user_id=?",
                (user_id,)
            ).fetchone()
        )
        ps=[
            dict(row)
            for row in con.execute(
                "SELECT * FROM garden_v2_plants WHERE user_id=? ORDER BY plot",
                (user_id,)
            )
        ]
        d=daily_con(con,user_id)
    return u,ps,d

def plant(guild_id,user_id,key):
    if key not in PLANTS:
        return {"ok":False,"reason":"plant"}

    cfg=PLANTS[key]

    with connect(True) as con:
        con.execute("BEGIN IMMEDIATE")
        touch_con(con,user_id)

        u=dict(
            con.execute(
                "SELECT * FROM garden_v2_users WHERE user_id=?",
                (user_id,)
            ).fetchone()
        )

        if lvl(u["xp"])<cfg["level"]:
            return {
                "ok":False,
                "reason":"level",
                "level":cfg["level"]
            }

        occupied={
            row["plot"]
            for row in con.execute(
                "SELECT plot FROM garden_v2_plants WHERE user_id=?",
                (user_id,)
            )
        }

        plot=next(
            (
                i
                for i in range(1,u["plots"]+1)
                if i not in occupied
            ),
            None
        )

        if plot is None:
            return {"ok":False,"reason":"full"}

        con.execute(
            "INSERT OR IGNORE INTO econ.wallets(guild_id,user_id) VALUES(?,?)",
            (guild_id,user_id)
        )

        cur=con.execute(
            "UPDATE econ.wallets SET roses=roses-? WHERE guild_id=? AND user_id=? AND roses>=?",
            (cfg["cost"],guild_id,user_id,cfg["cost"])
        )

        if cur.rowcount!=1:
            roses=con.execute(
                "SELECT roses FROM econ.wallets WHERE guild_id=? AND user_id=?",
                (guild_id,user_id)
            ).fetchone()["roses"]

            return {
                "ok":False,
                "reason":"broke",
                "need":max(0,cfg["cost"]-roses)
            }

        now=time.time()
        ready=now+cfg["seconds"]

        con.execute(
            """INSERT INTO garden_v2_plants(
                user_id,guild_id,plot,plant,planted_at,ready_at,deposit
            ) VALUES(?,?,?,?,?,?,?)""",
            (
                user_id,
                guild_id,
                plot,
                key,
                now,
                ready,
                cfg["cost"]
            )
        )

        con.execute(
            """UPDATE garden_v2_daily
            SET planted=planted+1
            WHERE user_id=? AND day=?""",
            (user_id,game.day().isoformat())
        )

        legacy_bump(con,user_id,"plant",1)
        legacy_user(con,user_id,u["xp"],u["plots"])
        legacy_plant(con,user_id,plot,key,now)

    return {
        "ok":True,
        "plot":plot,
        "plant":key,
        "ready":ready,
        "cost":cfg["cost"]
    }

def plant_all(guild_id,user_id,key):
    if key not in PLANTS:
        return {"ok":False,"reason":"plant"}

    cfg=PLANTS[key]

    with connect(True) as con:
        con.execute("BEGIN IMMEDIATE")
        touch_con(con,user_id)

        u=dict(
            con.execute(
                "SELECT * FROM garden_v2_users WHERE user_id=?",
                (user_id,)
            ).fetchone()
        )

        if lvl(u["xp"])<cfg["level"]:
            return {
                "ok":False,
                "reason":"level",
                "level":cfg["level"]
            }

        occupied={
            row["plot"]
            for row in con.execute(
                "SELECT plot FROM garden_v2_plants WHERE user_id=?",
                (user_id,)
            )
        }

        plots=[
            i
            for i in range(1,u["plots"]+1)
            if i not in occupied
        ]

        if not plots:
            return {"ok":False,"reason":"full"}

        total=cfg["cost"]*len(plots)

        con.execute(
            "INSERT OR IGNORE INTO econ.wallets(guild_id,user_id) VALUES(?,?)",
            (guild_id,user_id)
        )

        cur=con.execute(
            "UPDATE econ.wallets SET roses=roses-? WHERE guild_id=? AND user_id=? AND roses>=?",
            (total,guild_id,user_id,total)
        )

        if cur.rowcount!=1:
            roses=con.execute(
                "SELECT roses FROM econ.wallets WHERE guild_id=? AND user_id=?",
                (guild_id,user_id)
            ).fetchone()["roses"]

            return {
                "ok":False,
                "reason":"broke",
                "need":max(0,total-roses)
            }

        now=time.time()
        ready=now+cfg["seconds"]

        con.executemany(
            """INSERT INTO garden_v2_plants(
                user_id,guild_id,plot,plant,planted_at,ready_at,deposit
            ) VALUES(?,?,?,?,?,?,?)""",
            [
                (
                    user_id,
                    guild_id,
                    plot,
                    key,
                    now,
                    ready,
                    cfg["cost"]
                )
                for plot in plots
            ]
        )

        con.execute(
            """UPDATE garden_v2_daily
            SET planted=planted+?
            WHERE user_id=? AND day=?""",
            (
                len(plots),
                user_id,
                game.day().isoformat()
            )
        )

        legacy_bump(con,user_id,"plant",len(plots))
        legacy_user(con,user_id,u["xp"],u["plots"])

        for plot in plots:
            legacy_plant(con,user_id,plot,key,now)

    return {
        "ok":True,
        "plots":plots,
        "plant":key,
        "ready":ready,
        "cost":total,
        "count":len(plots)
    }

def uproot(user_id,plot):
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        touch_con(con,user_id)

        row=con.execute(
            """SELECT plant,deposit
            FROM garden_v2_plants
            WHERE user_id=? AND plot=?""",
            (user_id,plot)
        ).fetchone()

        if row is None:
            return {"ok":False}

        key=row["plant"]
        deposit=int(row["deposit"])

        con.execute(
            "DELETE FROM garden_v2_plants WHERE user_id=? AND plot=?",
            (user_id,plot)
        )

        con.execute(
            """UPDATE garden_v2_daily
            SET planted=MAX(harvested,planted-1)
            WHERE user_id=? AND day=?""",
            (user_id,game.day().isoformat())
        )

        legacy_delete(con,user_id,[plot])

    return {
        "ok":True,
        "plant":key,
        "plot":plot,
        "deposit":deposit
    }

def harvest(
    user_id,
    guild_id
):
    now=time.time()

    with connect(
        True
    ) as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        touch_con(
            con,
            user_id
        )

        rows=[
            dict(
                row
            )
            for row in con.execute(
                """SELECT *
                FROM garden_v2_plants
                WHERE user_id=?
                AND ready_at<=?
                ORDER BY plot""",
                (
                    user_id,
                    now
                )
            )
        ]

        if not rows:
            return {
                "ok":False
            }

        u=dict(
            con.execute(
                """SELECT *
                FROM garden_v2_users
                WHERE user_id=?""",
                (
                    user_id,
                )
            ).fetchone()
        )

        daily_cap=cap(
            u[
                "xp"
            ]
        )

        d=daily_con(
            con,
            user_id
        )

        varieties=set(
            d[
                "varieties"
            ]
        )

        remaining=max(
            0,
            daily_cap
            -int(
                d[
                    "profit"
                ]
            )
        )

        groups={}
        payouts={}
        wallet_profit={}
        refund=0
        paid=0
        potential=0
        xp=0
        plots=[]

        known=collection(
            user_id,
            con
        )

        discovered=[]

        knowing=(
            lvl(
                u[
                    "xp"
                ]
            )>=40
            and len(
                known
            )>=len(
                ORDER
            )
        )

        knowledge=0

        for row in rows:
            key=row[
                "plant"
            ]

            cfg=PLANTS.get(
                key
            )

            if cfg is None:
                continue

            wallet_guild=row[
                "guild_id"
            ]

            if wallet_guild is None:
                raise RuntimeError(
                    "garden plant wallet guild missing"
                )

            amount=min(
                cfg[
                    "profit"
                ],
                remaining
            )

            remaining-=amount

            refund+=int(
                row[
                    "deposit"
                ]
            )

            paid+=amount

            potential+=cfg[
                "profit"
            ]

            xp+=cfg[
                "xp"
            ]

            if knowing:
                knowledge+=(
                    cfg[
                        "profit"
                    ]
                    -amount
                )

            varieties.add(
                key
            )

            if key not in known:
                cur=con.execute(
                    """INSERT OR IGNORE INTO garden_v2_collection(
                        user_id,
                        plant,
                        found_at
                    ) VALUES(?,?,?)""",
                    (
                        user_id,
                        key,
                        now
                    )
                )

                if cur.rowcount:
                    known.add(
                        key
                    )

                    discovered.append(
                        key
                    )

            plots.append(
                row[
                    "plot"
                ]
            )

            group=groups.setdefault(
                key,
                {
                    "count":0,
                    "refund":0,
                    "profit":0,
                    "potential":0,
                    "xp":0
                }
            )

            group[
                "count"
            ]+=1

            group[
                "refund"
            ]+=int(
                row[
                    "deposit"
                ]
            )

            group[
                "profit"
            ]+=amount

            group[
                "potential"
            ]+=cfg[
                "profit"
            ]

            group[
                "xp"
            ]+=cfg[
                "xp"
            ]

            payouts[
                wallet_guild
            ]=(
                payouts.get(
                    wallet_guild,
                    0
                )
                +int(
                    row[
                        "deposit"
                    ]
                )
                +amount
            )

            wallet_profit[
                wallet_guild
            ]=(
                wallet_profit.get(
                    wallet_guild,
                    0
                )
                +amount
            )

        bouquet_new=(
            not bool(
                d[
                    "bouquet"
                ]
            )
            and len(
                varieties
            )>=3
        )

        bouquet_bonus=0
        bouquet=int(
            d[
                "bouquet"
            ]
        )

        if bouquet_new:
            bouquet=1

            bouquet_bonus=min(
                BOUQUET,
                remaining
            )

            paid+=bouquet_bonus
            remaining-=bouquet_bonus

            payouts[
                guild_id
            ]=(
                payouts.get(
                    guild_id,
                    0
                )
                +bouquet_bonus
            )

            wallet_profit[
                guild_id
            ]=(
                wallet_profit.get(
                    guild_id,
                    0
                )
                +bouquet_bonus
            )

        new_profit=min(
            daily_cap,
            int(
                d[
                    "profit"
                ]
            )
            +paid
        )

        level_after=lvl(
            int(
                u[
                    "xp"
                ]
            )
            +xp
            +knowledge
        )

        butterfly_plot=roll_butterfly(
            con,
            user_id,
            level_after,
            plots,
            now
        )

        garden_event=None
        event_xp=0

        if butterfly_plot is not None:
            record_garden_event(
                con,
                user_id,
                "butterfly",
                level_after,
                butterfly_plot,
                {
                    "rosarium":
                        "butterfly"
                },
                now
            )

        else:
            garden_event=roll_garden_event(
                level_after,
                plots
            )

            if garden_event:
                event_xp=apply_garden_event(
                    con,
                    user_id,
                    garden_event
                )

                reward={
                    "gxp":
                        int(
                            garden_event.get(
                                "gxp",
                                0
                            )
                        ),
                    "ingredients":
                        garden_event.get(
                            "ingredients",
                            {}
                        )
                }

                record_garden_event(
                    con,
                    user_id,
                    garden_event[
                        "key"
                    ],
                    level_after,
                    garden_event[
                        "plot"
                    ],
                    reward,
                    now
                )

        for wallet_guild,amount in payouts.items():
            con.execute(
                """INSERT OR IGNORE INTO econ.wallets(
                    guild_id,user_id
                ) VALUES(?,?)""",
                (
                    wallet_guild,
                    user_id
                )
            )

            con.execute(
                """UPDATE econ.wallets
                SET roses=roses+?
                WHERE guild_id=?
                AND user_id=?""",
                (
                    amount,
                    wallet_guild,
                    user_id
                )
            )

        total_xp=(
            xp
            +knowledge
            +event_xp
        )

        con.execute(
            """UPDATE garden_v2_users
            SET xp=xp+?
            WHERE user_id=?""",
            (
                total_xp,
                user_id
            )
        )

        con.executemany(
            """DELETE FROM garden_v2_plants
            WHERE user_id=?
            AND plot=?""",
            [
                (
                    user_id,
                    plot
                )
                for plot in plots
            ]
        )

        con.execute(
            """UPDATE garden_v2_daily
            SET profit=?,
                bouquet=?,
                varieties=?,
                harvested=harvested+?
            WHERE user_id=?
            AND day=?""",
            (
                new_profit,
                bouquet,
                json.dumps(
                    sorted(
                        varieties
                    )
                ),
                len(
                    plots
                ),
                user_id,
                game.day().isoformat()
            )
        )

        legacy_bump(
            con,
            user_id,
            "harvest",
            len(
                plots
            )
        )

        legacy_user(
            con,
            user_id,
            int(
                u[
                    "xp"
                ]
            )
            +total_xp,
            u[
                "plots"
            ]
        )

        legacy_delete(
            con,
            user_id,
            plots
        )

    return {
        "ok":True,
        "groups":groups,
        "refund":refund,
        "profit":paid,
        "wallet_profit":
            wallet_profit,
        "potential":potential,
        "xp":xp,
        "knowledge":knowledge,
        "event_xp":event_xp,
        "daily":new_profit,
        "cap":daily_cap,
        "bouquet_new":
            bouquet_new,
        "bouquet_bonus":
            bouquet_bonus,
        "clipped":
            potential
            +(
                BOUQUET
                if bouquet_new
                else 0
            )
            >paid,
        "new":discovered,
        "garden_event":
            garden_event,
        "butterfly_plot":
            butterfly_plot,
        "level":lvl(
            int(
                u[
                    "xp"
                ]
            )
            +total_xp
        )
    }

def unlock(guild_id,user_id):
    with connect(True) as con:
        con.execute("BEGIN IMMEDIATE")
        touch_con(con,user_id)

        u=dict(
            con.execute(
                "SELECT * FROM garden_v2_users WHERE user_id=?",
                (user_id,)
            ).fetchone()
        )

        if u["plots"]>=5:
            return {
                "ok":False,
                "reason":"max"
            }

        plot=u["plots"]+1
        level_req,cost=PLOT_REQ[plot]

        if lvl(u["xp"])<level_req:
            return {
                "ok":False,
                "reason":"level",
                "level":level_req
            }

        con.execute(
            "INSERT OR IGNORE INTO econ.wallets(guild_id,user_id) VALUES(?,?)",
            (guild_id,user_id)
        )

        cur=con.execute(
            "UPDATE econ.wallets SET roses=roses-? WHERE guild_id=? AND user_id=? AND roses>=?",
            (cost,guild_id,user_id,cost)
        )

        if cur.rowcount!=1:
            roses=con.execute(
                "SELECT roses FROM econ.wallets WHERE guild_id=? AND user_id=?",
                (guild_id,user_id)
            ).fetchone()["roses"]

            return {
                "ok":False,
                "reason":"broke",
                "need":max(0,cost-roses)
            }

        con.execute(
            "UPDATE garden_v2_users SET plots=? WHERE user_id=?",
            (plot,user_id)
        )

        legacy_user(
            con,
            user_id,
            u["xp"],
            plot
        )

    return {
        "ok":True,
        "plot":plot,
        "cost":cost
    }

def bar(value):
    filled=min(
        10,
        max(
            0,
            int(value*10/CAP)
        )
    )
    return "▰"*filled+"▱"*(10-filled)

def numeral(n):
    return ("Ⅰ","Ⅱ","Ⅲ","Ⅳ","Ⅴ")[n-1]

def rules_embed():
    lines=[]

    for key in ORDER:
        p=PLANTS[key]

        lines.append(
            f"{p['emoji']} **{p['name']}** ⊹ "
            f"{p['cost']:,} dep • "
            f"{duration(p['seconds'])} • "
            f"+{p['profit']:,} roses • "
            f"{p['xp']:,} GXP • "
            f"lvl {p['level']}"
        )

    embed=discord.Embed(
        title=rosieemoji.ROSE + ' garden',
        description=(
            '🌱 plant • wait • ✂️ harvest\ndeposit ⊹ returned at harvest\nbloom ⊹ **1,250 + 50/lvl ' + rosieemoji.ROSE + ' • 3,000 max**\n💐 3 varieties ⊹ **+100 ' + rosieemoji.ROSE + '**\ncollection ⊹ first harvests stay'
        ),
        color=discord.Color.dark_red()
    )

    embed.add_field(
        name="🌼 plants",
        value="\n".join(lines),
        inline=False
    )

    return embed

def harvest_embed(
    result
):
    lines=[]

    for key,data in result[
        "groups"
    ].items():
        p=PLANTS[
            key
        ]

        mult=(
            f" ×{data['count']}"
            if data[
                "count"
            ]>1
            else ""
        )

        lines.append(
            f"{p['emoji']} "
            f"**{p['name']}{mult}** "
            f"⊹ ↩️ {data['refund']:,} "
            f"{rosieemoji.ROSE} "
            f"• +{data['profit']:,} "
            f"{rosieemoji.ROSE} "
            f"• +{data['xp']:,} GXP"
        )

    if result.get(
        "knowledge"
    ):
        lines.append(
            f"{rosieemoji.ROSE} ⊹ "
            f"+{result['knowledge']:,} "
            "knowledge GXP"
        )

    if result[
        "bouquet_new"
    ]:
        lines.append(
            (
                f"💐 ⊹ "
                f"+{result['bouquet_bonus']:,} "
                f"{rosieemoji.ROSE}"
            )
            if result[
                "bouquet_bonus"
            ]
            else "💐 ⊹ complete"
        )

    if result.get(
        "new"
    ):
        found=" • ".join(
            f"{PLANTS[key]['emoji']} "
            f"{PLANTS[key]['name']}"
            for key in result[
                "new"
            ]
        )

        lines.append(
            f"✦ ⊹ {found}"
        )

    lines.append(
        f"bloom ⊹ "
        f"**{result['daily']:,}/"
        f"{result['cap']:,} "
        f"{rosieemoji.ROSE}**"
    )

    event=result.get(
        "garden_event"
    )

    if event:
        lines.extend((
            "",
            f"{event['emoji']} "
            f"**{event['label']}**",
            event[
                "text"
            ],
            f"reward ⊹ "
            f"**{garden_event_reward(event)}**"
        ))

    if result.get(
        "butterfly_plot"
    ) is not None:
        lines.extend((
            "",
            f"🦋 **a butterfly flew onto "
            f"plot {result['butterfly_plot']}.**",
            "it doesn't seem to be leaving."
        ))

    embed=discord.Embed(
        title="✦ harvest",
        description="\n".join(
            lines
        ),
        color=discord.Color.dark_red()
    )

    if result[
        "clipped"
    ]:
        embed.set_footer(
            text=(
                "daily bloom maxed • "
                "overflow became knowledge GXP"
                if result.get(
                    "knowledge"
                )
                else (
                    "daily bloom maxed • "
                    "refunds + GXP still count"
                )
            )
        )

    return embed

class PlantSelect(discord.ui.Select):
    def __init__(self,parent,message,all=False):
        self.garden=parent
        self.garden_message=message
        self.all=all

        u,ps,d=state(parent.user_id)
        level=lvl(u["xp"])
        options=[]

        for key in ORDER:
            p=PLANTS[key]
            locked=level<p["level"]

            label=(
                f"{p['name']} ⊹ lvl {p['level']}"
                if locked
                else p["name"]
            )

            desc=(
                f"{p['cost']:,} dep • "
                f"{duration(p['seconds'])} • "
                f"+{p['profit']:,} roses • "
                f"{p['xp']:,} GXP"
            )

            options.append(
                discord.SelectOption(
                    label=label[:100],
                    description=desc[:100],
                    value=key,
                    emoji=p["emoji"]
                )
            )

        super().__init__(
            placeholder="pick a flower",
            options=options
        )

    async def callback(self,it:discord.Interaction):
        if it.user.id!=self.garden.viewer_id:
            await it.response.send_message(
                "make ur own /garden",
                ephemeral=True
            )
            return

        lock=LOCKS.setdefault(
            it.user.id,
            asyncio.Lock()
        )

        async with lock:
            result=(
                plant_all(
                    it.guild.id,
                    it.user.id,
                    self.values[0]
                )
                if self.all
                else plant(
                    it.guild.id,
                    it.user.id,
                    self.values[0]
                )
            )

        if not result["ok"]:
            if result["reason"]=="level":
                text=(
                    f"that flower unlocks at "
                    f"level {result['level']}"
                )
            elif result["reason"]=="full":
                text="ur garden is full"
            elif result["reason"]=="broke":
                text=(
                    f"broke broski you need {result['need']:,} more {rosieemoji.ROSE}"
                )
            else:
                text="cant plant that"

            await it.response.send_message(
                text,
                ephemeral=True
            )
            return

        self.garden.sync()

        try:
            await self.garden_message.edit(
                embed=self.garden.embed(),
                view=self.garden
            )
        except discord.HTTPException:
            pass

        p=PLANTS[result["plant"]]

        if self.all:
            plots=", ".join(
                numeral(x)
                for x in result["plots"]
            )

            text=(
                f"{p['emoji']} **{p['name']} ×{result['count']}** "
                f"⊹ {plots}\n"
                f"ready <t:{int(result['ready'])}:R>"
            )
        else:
            text=(
                f"{p['emoji']} **{p['name']}** "
                f"⊹ {numeral(result['plot'])}\n"
                f"ready <t:{int(result['ready'])}:R>"
            )

        await it.response.send_message(
            text,
            ephemeral=True
        )

class PlantView(discord.ui.View):
    def __init__(self,parent,message,all=False):
        super().__init__(timeout=60)
        self.add_item(
            PlantSelect(
                parent,
                message,
                all
            )
        )

class UprootView(discord.ui.View):
    def __init__(self,garden,plot,message,row):
        super().__init__(timeout=60)

        self.garden=garden
        self.plot=plot
        self.message=message
        self.row=row

    async def interaction_check(self,it:discord.Interaction):
        if (
            it.user.id==self.garden.viewer_id
            and not self.garden.readonly
        ):
            return True

        await it.response.send_message(
            "make ur own /garden",
            ephemeral=True
        )
        return False

    @discord.ui.button(
        emoji="🗑️",
        style=discord.ButtonStyle.danger
    )
    async def yes(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        lock=LOCKS.setdefault(
            self.garden.user_id,
            asyncio.Lock()
        )

        async with lock:
            result=uproot(
                self.garden.user_id,
                self.plot
            )

        if not result["ok"]:
            await it.response.edit_message(
                content="that plot already moved",
                view=None
            )
            return

        self.garden.sync()

        try:
            await self.message.edit(
                embed=self.garden.embed(),
                view=self.garden
            )
        except discord.HTTPException:
            pass

        p=PLANTS[result["plant"]]

        await it.response.edit_message(
            content=(
                f"🗑️ **{p['name']}** ⊹ {numeral(self.plot)}\nlost ⊹ **{result['deposit']:,} {rosieemoji.ROSE}**"
            ),
            view=None
        )

    @discord.ui.button(
        emoji="↩️",
        style=discord.ButtonStyle.secondary
    )
    async def no(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        await it.response.edit_message(
            content="kept it 🌱",
            view=None
        )

class UnlockConfirmView(discord.ui.View):
    def __init__(
        self,
        garden,
        plot,
        message
    ):
        super().__init__(
            timeout=45
        )

        self.garden=garden
        self.plot=plot
        self.message=message

    async def interaction_check(
        self,
        it:discord.Interaction
    ):
        if (
            it.user.id
            ==self.garden.viewer_id
            and not self.garden.readonly
        ):
            return True

        await it.response.send_message(
            "make ur own /garden",
            ephemeral=True
        )

        return False

    @discord.ui.button(
        emoji="🔓",
        style=discord.ButtonStyle.success
    )
    async def yes(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        lock=LOCKS.setdefault(
            self.garden.user_id,
            asyncio.Lock()
        )

        async with lock:
            u,ps,d=state(
                self.garden.user_id
            )

            if (
                self.plot
                !=u["plots"]+1
            ):
                await it.response.edit_message(
                    content="that plot already moved",
                    view=None
                )
                return

            req,cost=PLOT_REQ[
                self.plot
            ]

            if lvl(u["xp"])<req:
                await it.response.edit_message(
                    content=(
                        f"plot {self.plot} "
                        f"unlocks at level {req}"
                    ),
                    view=None
                )
                return

            result=unlock(
                it.guild.id,
                self.garden.user_id
            )

        if not result["ok"]:
            if result["reason"]=="broke":
                text=(
                    f"broke broski you need {result['need']:,} more {rosieemoji.ROSE}"
                )

            elif result["reason"]=="level":
                text=(
                    f"plot {self.plot} "
                    f"unlocks at level "
                    f"{result['level']}"
                )

            else:
                text="cant unlock that plot"

            await it.response.edit_message(
                content=text,
                view=None
            )
            return

        self.garden.sync()

        try:
            await self.message.edit(
                embed=self.garden.embed(),
                view=self.garden
            )
        except discord.HTTPException:
            pass

        await it.response.edit_message(
            content=(
                f"plot {self.plot} unlocked ⊹ -{result['cost']:,} {rosieemoji.ROSE}"
            ),
            view=None
        )

    @discord.ui.button(
        label="cancel",
        style=discord.ButtonStyle.secondary
    )
    async def no(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        await it.response.edit_message(
            content="kept it locked",
            view=None
        )


class PlotCell(discord.ui.Button):
    def __init__(self,garden,plot):
        self.garden=garden
        self.plot=plot

        super().__init__(
            label=str(plot),
            style=discord.ButtonStyle.secondary,
            row=0 if plot<=3 else 1
        )

    async def callback(self,it:discord.Interaction):
        if it.user.id!=self.garden.viewer_id:
            await it.response.send_message(
                "make ur own /garden",
                ephemeral=True
            )
            return

        u,ps,d=state(
            self.garden.user_id
        )

        if self.plot>u["plots"]:
            req,cost=PLOT_REQ[
                self.plot
            ]

            if self.garden.readonly:
                await it.response.send_message(
                    f'🔒 plot {self.plot}\nlvl {req} ⊹ {cost:,} {rosieemoji.ROSE}',
                    ephemeral=True
                )
                return

            if (
                self.plot
                !=u["plots"]+1
            ):
                await it.response.send_message(
                    f"unlock plot {u['plots']+1} first",
                    ephemeral=True
                )
                return

            if lvl(u["xp"])<req:
                await it.response.send_message(
                    f"plot {self.plot} unlocks "
                    f"at level {req}",
                    ephemeral=True
                )
                return

            await it.response.send_message(
                (
                    f'unlock plot {self.plot}?\ncost ⊹ **{cost:,} roses {rosieemoji.ROSE}**'
                ),
                view=UnlockConfirmView(
                    self.garden,
                    self.plot,
                    it.message
                ),
                ephemeral=True
            )
            return

        row=next(
            (
                row
                for row in ps
                if row["plot"]==self.plot
            ),
            None
        )

        if row is None:
            await it.response.send_message(
                f"{numeral(self.plot)} ⊹ empty",
                ephemeral=True
            )
            return

        p=PLANTS[
            row["plant"]
        ]

        status=(
            "ready ✦"
            if row["ready_at"]<=time.time()
            else (
                f"<t:{int(row['ready_at'])}:R>"
            )
        )

        text=(
            f"{p['emoji']} **{p['name']}** ⊹ {status}\n{row['deposit']:,} {rosieemoji.ROSE} dep • +{p['profit']:,} {rosieemoji.ROSE} • {p['xp']:,} GXP"
        )

        if self.garden.readonly:
            await it.response.send_message(
                text,
                ephemeral=True
            )
            return


        await it.response.send_message(
            text,
            view=UprootView(
                self.garden,
                self.plot,
                it.message,
                row
            ),
            ephemeral=True
        )

class GardenView(discord.ui.View):
    def __init__(
        self,
        user_id,
        display_name,
        viewer_id=None,
        readonly=False
    ):
        super().__init__(
            timeout=600
        )

        self.user_id=user_id
        self.viewer_id=viewer_id or user_id
        self.readonly=readonly
        self.display_name=display_name

        # Decorated buttons already exist after View.__init__.
        # Remove the secret button so we can add it after plots 4 + 5.
        secret=self.secret_button
        self.remove_item(
            secret
        )

        # Always render all five plot positions.
        for plot in range(1,6):
            self.add_item(
                PlotCell(
                    self,
                    plot
                )
            )

        # Sixth grid slot.
        secret.row=1
        secret.label=None
        self.add_item(
            secret
        )

        self.sync()

    def owned(self,it):
        return (
            it.user.id
            ==self.viewer_id
        )

    def sync(self):
        u,ps,d=state(
            self.user_id
        )

        planted={
            row["plot"]:row
            for row in ps
        }

        occupied=set(
            planted
        )

        for item in self.children:
            if not isinstance(
                item,
                PlotCell
            ):
                continue

            plot=item.plot

            if plot>u["plots"]:
                item.label=str(plot)
                item.emoji="🔒"
                item.style=discord.ButtonStyle.secondary
                item.disabled=self.readonly
                continue

            row=planted.get(
                plot
            )

            if row is None:
                item.label=str(plot)
                item.emoji=None
                item.style=discord.ButtonStyle.secondary
                item.disabled=False
                continue

            p=PLANTS[
                row["plant"]
            ]

            item.label=str(plot)

            item.emoji=p["emoji"]

            item.style=(
                discord.ButtonStyle.success
                if row["ready_at"]<=time.time()
                else discord.ButtonStyle.danger
            )

            item.disabled=False

        self.plant_button.disabled=(
            self.readonly
            or all(
                plot in occupied
                for plot in range(
                    1,
                    u["plots"]+1
                )
            )
        )

        self.plant_all_button.disabled=(
            self.plant_button.disabled
        )

        self.harvest_button.disabled=(
            self.readonly
            or not any(
                row["ready_at"]<=time.time()
                for row in ps
            )
        )

        unlocked=allknowing(
            self.user_id
        )

        self.secret_button.label=None

        self.secret_button.emoji=(
            rosieemoji.ROSE
            if unlocked
            else "❔"
        )

        self.secret_button.style=(
            discord.ButtonStyle.success
            if unlocked
            else discord.ButtonStyle.secondary
        )

        self.secret_button.disabled=(
            self.readonly
        )

    def embed(self):
        u,ps,d=state(
            self.user_id
        )

        level=lvl(
            u["xp"]
        )

        progress=(
            u["xp"]%250
        )

        daily_cap=cap(
            u["xp"]
        )

        status=[]

        for row in sorted(
            ps,
            key=lambda row:row["plot"]
        ):
            p=PLANTS[
                row["plant"]
            ]

            if row["ready_at"]<=time.time():
                status.append(
                    f"{p['emoji']} "
                    f"{p['name']} ⊹ ready ✦"
                )
            else:
                status.append(
                    f"{p['emoji']} "
                    f"{p['name']} ⊹ "
                    f"<t:{int(row['ready_at'])}:R>"
                )

        if not status:
            status=[
                "nothing growing 🌱"
            ]

        bouquet=(
            "💐 complete"
            if d["bouquet"]
            else (
                f"💐 "
                f"{len(d['varieties'])}/3"
            )
        )

        got=collection(
            self.user_id
        )

        return discord.Embed(
            title=(
                f"{rosieemoji.ROSE} {self.display_name}'s garden"
            ),
            description=(
                f"lvl **{level}** ⊹ **{progress:,}/250 GXP**\nbloom ⊹ **{d['profit']:,}/{daily_cap:,} {rosieemoji.ROSE}** • {bouquet}\ncollection ⊹ **{len(got)} / {len(ORDER)}**\n\n"
                +"\n".join(status)
            ),
            color=discord.Color.dark_red()
        )

    @discord.ui.button(
        emoji="🌱",
        style=discord.ButtonStyle.danger,
        row=2
    )
    async def plant_button(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        if not self.owned(it):
            await it.response.send_message(
                "make ur own /garden",
                ephemeral=True
            )
            return

        if self.readonly:
            return

        await it.response.send_message(
            "🌱 pick a plant",
            view=PlantView(
                self,
                it.message
            ),
            ephemeral=True
        )

    @discord.ui.button(
        emoji="🌿",
        style=discord.ButtonStyle.danger,
        row=2
    )
    async def plant_all_button(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        if not self.owned(it):
            await it.response.send_message(
                "make ur own /garden",
                ephemeral=True
            )
            return

        if self.readonly:
            return

        await it.response.send_message(
            "🌿 fill empty plots",
            view=PlantView(
                self,
                it.message,
                True
            ),
            ephemeral=True
        )

    @discord.ui.button(
        emoji="✂️",
        style=discord.ButtonStyle.success,
        row=2
    )
    async def harvest_button(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        if not self.owned(it):
            await it.response.send_message(
                "make ur own /garden",
                ephemeral=True
            )
            return

        if self.readonly:
            return

        lock=LOCKS.setdefault(
            self.user_id,
            asyncio.Lock()
        )

        async with lock:
            result=harvest(
                self.user_id,
                it.guild.id
            )

        self.sync()

        await it.response.edit_message(
            embed=self.embed(),
            view=self
        )

        if result["ok"]:
            await it.followup.send(
                embed=harvest_embed(
                    result
                ),
                ephemeral=True
            )

    @discord.ui.button(
        emoji="❔",
        style=discord.ButtonStyle.secondary,
        row=2
    )
    async def secret_button(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        if not self.owned(it):
            await it.response.send_message(
                "make ur own /garden",
                ephemeral=True
            )
            return

        if self.readonly:
            return

        await it.response.send_message(
            embed=collection_embed(
                self.user_id
            ),
            ephemeral=True
        )

    @discord.ui.button(
        emoji="❓",
        style=discord.ButtonStyle.secondary,
        row=2
    )
    async def rules_button(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        if not self.owned(it):
            await it.response.send_message(
                "make ur own /garden",
                ephemeral=True
            )
            return

        await it.response.defer(
            ephemeral=True
        )

        try:
            embed=rules_embed()

            await it.followup.send(
                embed=embed,
                ephemeral=True
            )

        except Exception as error:
            print(
                f"garden rules error ⊹ {error!r}"
            )

            await it.followup.send(
                "garden rules tripped 💔",
                ephemeral=True
            )

def garden_exists(user_id):
    with connect() as con:
        row=con.execute(
            """SELECT 1
            FROM garden_v2_users
            WHERE user_id=?""",
            (user_id,)
        ).fetchone()

        if row:
            return True

        row=con.execute(
            """SELECT 1
            FROM garden_v2_plants
            WHERE user_id=?
            LIMIT 1""",
            (user_id,)
        ).fetchone()

        return row is not None

class Garden(commands.Cog):
    @app_commands.command(
        name="garden",
        description="grow your garden"
    )
    @app_commands.describe(
        user='user',
        user_id='user id'
    )
    async def garden(
        self,
        it:discord.Interaction,
        user:discord.User|None=None,
        user_id:str|None=None
    ):
        await it.response.defer()

        try:
            if (
                user is not None
                and user_id is not None
            ):
                await it.followup.send(
                    "pick a user or user id, not both",
                    ephemeral=True
                )
                return

            if user is not None:
                target_id=user.id
                name=getattr(
                    user,
                    "display_name",
                    user.name
                )

            elif user_id is not None:
                raw=user_id.strip()
                raw=(
                    raw
                    .replace("<@","")
                    .replace("!","")
                    .replace(">","")
                )

                try:
                    target_id=int(
                        raw
                    )
                except ValueError:
                    await it.followup.send(
                        "gimme a real user id",
                        ephemeral=True
                    )
                    return

                member=(
                    it.guild.get_member(
                        target_id
                    )
                    if it.guild
                    else None
                )

                cached=it.client.get_user(
                    target_id
                )

                if member:
                    name=member.display_name
                elif cached:
                    name=getattr(
                        cached,
                        "display_name",
                        cached.name
                    )
                else:
                    name=f"user {target_id}"

            else:
                target_id=it.user.id
                name=it.user.display_name

            if target_id==it.user.id:
                game.touch(
                    target_id
                )

            elif not garden_exists(
                target_id
            ):
                await it.followup.send(
                    "they dont have a garden yet",
                    ephemeral=True
                )
                return

            readonly=(
                target_id!=it.user.id
            )

            view=GardenView(
                target_id,
                name,
                viewer_id=it.user.id,
                readonly=readonly
            )

            await it.followup.send(
                embed=view.embed(),
                view=view
            )

        except Exception as e:
            print(
                f"garden command: "
                f"{type(e).__name__}: {e}"
            )

            await it.followup.send(
                "garden tripped 💔",
                ephemeral=True
            )

async def setup(bot):
    init()
    await bot.add_cog(
        Garden()
    )
