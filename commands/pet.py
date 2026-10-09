import hashlib
import secrets
import sqlite3
import time

import discord
from core import database
from core import game
from core import petcatalog
from discord import app_commands
from discord.ext import commands
from core import emoji as rosieemoji

MAX_LEVEL=50
FEED_CD=14400
PLAY_CD=10800
EXPLORE_CD=7200
FEED_COST=150
PLAY_COST=75
RENAME_COST=1000
SPECIES=petcatalog.SPECIES
TIER_ORDER=petcatalog.TIER_ORDER

TIER_LABELS={
    "base":"sprout",
    "mid":"bud",
    "high":"blossom",
    "rosarium":"rosarium"
}

EXPLORE=(
    (2500,50,"came back filthy"),
    (3500,85,"found some petals"),
    (2500,125,"brought something useful"),
    (1000,250,"found a rose stash"),
    (400,500,"found something lucky"),
    (100,1000,"found something absurd")
)

def connect():
    con=sqlite3.connect(database.FILE,timeout=10)
    con.row_factory=sqlite3.Row
    return con

def init():
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS pet_users(
            user_id INTEGER PRIMARY KEY,
            active TEXT,
            earned INTEGER NOT NULL DEFAULT 0,
            spent INTEGER NOT NULL DEFAULT 0
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS pets(
            user_id INTEGER NOT NULL,
            species TEXT NOT NULL,
            name TEXT NOT NULL,
            named INTEGER NOT NULL DEFAULT 0,
            level INTEGER NOT NULL DEFAULT 1,
            xp INTEGER NOT NULL DEFAULT 0,
            affection INTEGER NOT NULL DEFAULT 60,
            energy INTEGER NOT NULL DEFAULT 100,
            energy_at REAL NOT NULL,
            adopted_at REAL NOT NULL,
            last_care REAL NOT NULL,
            decay_at REAL NOT NULL,
            last_feed REAL NOT NULL DEFAULT 0,
            last_play REAL NOT NULL DEFAULT 0,
            last_explore REAL NOT NULL DEFAULT 0,
            feeds INTEGER NOT NULL DEFAULT 0,
            plays INTEGER NOT NULL DEFAULT 0,
            explores INTEGER NOT NULL DEFAULT 0,
            earned INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id,species)
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS pet_finds(
            user_id INTEGER NOT NULL,
            species TEXT NOT NULL,
            item TEXT NOT NULL,
            found_at REAL NOT NULL,
            PRIMARY KEY(user_id,species,item)
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS pet_meta(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS pet_morphs(
            user_id INTEGER NOT NULL,
            old_species TEXT NOT NULL,
            new_species TEXT NOT NULL,
            roses INTEGER NOT NULL,
            migrated_at REAL NOT NULL,
            paid_at REAL,
            noticed_at REAL,
            PRIMARY KEY(user_id,old_species)
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS pet_rosarium(
            user_id INTEGER PRIMARY KEY,
            butterfly_encountered_at REAL,
            butterfly_adopted_at REAL
        )""")

        migrate_v2(
            con
        )

def need(level):
    return 20+level*5

def levelup(level,xp,amount):
    xp+=amount
    gained=0
    while level<MAX_LEVEL and xp>=need(level):
        xp-=need(level)
        level+=1
        gained+=1
    if level>=MAX_LEVEL:
        xp=0
    return level,xp,gained

def clean(name):
    name=" ".join(name.strip().split())
    return name if 1<=len(name)<=20 else None

def shown(name):
    return discord.utils.escape_markdown(name.replace("@","@\u200b"))

def touch(con,user_id):
    con.execute("INSERT OR IGNORE INTO pet_users(user_id) VALUES(?)",(user_id,))

def highest(con,user_id):
    row=con.execute("SELECT MAX(level) FROM pets WHERE user_id=?",(user_id,)).fetchone()
    return int(row[0] or 0)


def migrate_v2(con):
    done=con.execute(
        """SELECT value
        FROM pet_meta
        WHERE key='roster_v2'"""
    ).fetchone()

    if done is not None:
        return

    now=time.time()

    tables={
        row["name"]
        for row in con.execute(
            """SELECT name
            FROM sqlite_master
            WHERE type='table'"""
        )
    }

    for old_species,cfg in petcatalog.MORPHS.items():
        rows=con.execute(
            """SELECT *
            FROM pets
            WHERE species=?
            ORDER BY user_id""",
            (
                old_species,
            )
        ).fetchall()

        new_species=cfg[
            "new"
        ]

        new_info=SPECIES[
            new_species
        ]

        for row in rows:
            user_id=int(
                row[
                    "user_id"
                ]
            )

            times=[
                float(found["found_at"])
                for found in con.execute(
                    """SELECT found_at
                    FROM pet_finds
                    WHERE user_id=?
                    AND species=?
                    ORDER BY found_at,item""",
                    (
                        user_id,
                        old_species
                    )
                ).fetchall()
            ]

            con.execute(
                """INSERT OR IGNORE INTO pet_morphs(
                    user_id,
                    old_species,
                    new_species,
                    roses,
                    migrated_at
                ) VALUES(?,?,?,?,?)""",
                (
                    user_id,
                    old_species,
                    new_species,
                    cfg[
                        "compensation"
                    ],
                    now
                )
            )

            con.execute(
                """DELETE FROM pet_finds
                WHERE user_id=?
                AND species=?""",
                (
                    user_id,
                    old_species
                )
            )

            name=(
                row[
                    "name"
                ]
                if row[
                    "named"
                ]
                else new_info[
                    "name"
                ]
            )

            con.execute(
                """UPDATE pets
                SET species=?,
                    name=?
                WHERE user_id=?
                AND species=?""",
                (
                    new_species,
                    name,
                    user_id,
                    old_species
                )
            )

            for item,found_at in zip(
                new_info[
                    "finds"
                ],
                times
            ):
                con.execute(
                    """INSERT OR IGNORE INTO pet_finds(
                        user_id,
                        species,
                        item,
                        found_at
                    ) VALUES(?,?,?,?)""",
                    (
                        user_id,
                        new_species,
                        item,
                        found_at
                    )
                )

            con.execute(
                """UPDATE pet_users
                SET active=?
                WHERE user_id=?
                AND active=?""",
                (
                    new_species,
                    user_id,
                    old_species
                )
            )

        if "pet_buffs" in tables:
            con.execute(
                """UPDATE pet_buffs
                SET species=?
                WHERE species=?""",
                (
                    new_species,
                    old_species
                )
            )

    for species,info in SPECIES.items():
        con.execute(
            """UPDATE pets
            SET name=?
            WHERE species=?
            AND named=0""",
            (
                info[
                    "name"
                ],
                species
            )
        )

    con.execute(
        """INSERT INTO pet_meta(
            key,value
        ) VALUES(
            'roster_v2',
            '1'
        )"""
    )


def rosariumprogress(
    con,
    user_id
):
    marks=",".join(
        "?"
        for _ in petcatalog.NORMAL_SPECIES
    )

    owned_count=con.execute(
        f"""SELECT COUNT(DISTINCT species)
        FROM pets
        WHERE user_id=?
        AND species IN ({marks})""",
        (
            user_id,
            *petcatalog.NORMAL_SPECIES
        )
    ).fetchone()[0]

    special=con.execute(
        """SELECT butterfly_encountered_at,
                  butterfly_adopted_at
        FROM pet_rosarium
        WHERE user_id=?""",
        (
            user_id,
        )
    ).fetchone()

    garden_level=0

    try:
        with sqlite3.connect(
            game.DB
        ) as garden:
            row=garden.execute(
                """SELECT xp
                FROM garden_v2_users
                WHERE user_id=?""",
                (
                    user_id,
                )
            ).fetchone()

            if row is not None:
                garden_level=(
                    1
                    +int(
                        row[0]
                    )//250
                )

    except sqlite3.Error:
        pass

    encountered=bool(
        special
        and special[
            "butterfly_encountered_at"
        ]
    )

    adopted=bool(
        special
        and special[
            "butterfly_adopted_at"
        ]
    )

    eligible=(
        int(
            owned_count
        )>=petcatalog.ROSARIUM_NORMALS
        and garden_level>=
        petcatalog.ROSARIUM_GARDEN_LEVEL
    )

    return {
        "owned":int(
            owned_count
        ),
        "garden_level":
            garden_level,
        "eligible":
            eligible,
        "encountered":
            encountered,
        "adopted":
            adopted
    }


def available(
    con,
    user_id,
    species
):
    info=SPECIES[
        species
    ]

    if con.execute(
        """SELECT 1
        FROM pets
        WHERE user_id=?
        AND species=?""",
        (
            user_id,
            species
        )
    ).fetchone():
        return True

    if info[
        "tier"
    ]=="rosarium":
        return rosariumprogress(
            con,
            user_id
        )[
            "encountered"
        ]

    return (
        highest(
            con,
            user_id
        )
        >=int(
            info[
                "unlock"
            ]
        )
    )


def requirement(
    info
):
    if info[
        "tier"
    ]=="rosarium":
        return (
            f"all {petcatalog.ROSARIUM_NORMALS} "
            "normal pets + "
            f"garden lvl "
            f"{petcatalog.ROSARIUM_GARDEN_LEVEL:,} "
            "+ butterfly encounter"
        )

    level=int(
        info[
            "unlock"
        ]
    )

    return (
        "none"
        if level<=0
        else f"pet lvl {level}"
    )


def morph_notice(
    user_id,
    guild_id
):
    now=time.time()

    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        rows=con.execute(
            """SELECT *
            FROM pet_morphs
            WHERE user_id=?
            AND noticed_at IS NULL
            ORDER BY migrated_at,old_species""",
            (
                user_id,
            )
        ).fetchall()

        if not rows:
            return None

        unpaid=[
            row
            for row in rows
            if row[
                "paid_at"
            ] is None
        ]

        amount=sum(
            int(
                row[
                    "roses"
                ]
            )
            for row in unpaid
        )

        if amount:
            scope=database.walletscope(
                guild_id
            )

            con.execute(
                """INSERT OR IGNORE INTO wallets(
                    guild_id,user_id
                ) VALUES(?,?)""",
                (
                    scope,
                    user_id
                )
            )

            con.execute(
                """UPDATE wallets
                SET roses=roses+?
                WHERE guild_id=?
                AND user_id=?""",
                (
                    amount,
                    scope,
                    user_id
                )
            )

            con.execute(
                """UPDATE pet_morphs
                SET paid_at=?
                WHERE user_id=?
                AND paid_at IS NULL""",
                (
                    now,
                    user_id
                )
            )

        return {
            "rows":[
                dict(
                    row
                )
                for row in rows
            ],
            "total":sum(
                int(
                    row[
                        "roses"
                    ]
                )
                for row in rows
            )
        }


def mark_morph_noticed(
    user_id
):
    with connect() as con:
        con.execute(
            """UPDATE pet_morphs
            SET noticed_at=?
            WHERE user_id=?
            AND noticed_at IS NULL""",
            (
                time.time(),
                user_id
            )
        )


def morphembed(
    notice
):
    lines=[]

    for row in notice[
        "rows"
    ]:
        cfg=petcatalog.MORPHS[
            row[
                "old_species"
            ]
        ]

        new=SPECIES[
            row[
                "new_species"
            ]
        ]

        lines.append(
            f"{cfg['old_name']} → "
            f"{new['emoji']} **{new['name']}** "
            f"⊹ **+{int(row['roses']):,} roses "
            f"{rosieemoji.ROSE}**"
        )

    lines.extend((
        "",
        f"pet-morph compensation ⊹ "
        f"**+{notice['total']:,} roses "
        f"{rosieemoji.ROSE}**",
        "",
        "levels, xp, affection, stats, "
        "custom names and find progress were preserved"
    ))

    return discord.Embed(
        title="🐾 pet morph",
        description="\n".join(
            lines
        ),
        color=discord.Color.dark_red()
    )


def owned(con,user_id):
    rows=con.execute("SELECT * FROM pets WHERE user_id=? ORDER BY adopted_at",(user_id,)).fetchall()
    return {row["species"]:dict(row) for row in rows}

def fresh(con,user_id,species,now=None):
    now=now or time.time()
    row=con.execute("SELECT * FROM pets WHERE user_id=? AND species=?",(user_id,species)).fetchone()
    if row is None:
        return None
    data=dict(row)
    gain=max(0,int((now-data["energy_at"])//1200))
    energy=data["energy"]
    energy_at=data["energy_at"]
    if gain:
        energy=min(100,energy+gain)
        energy_at=now if energy>=100 else energy_at+gain*1200
    affection=data["affection"]
    start=max(data["decay_at"],data["last_care"]+172800)
    lost=0
    if now>start:
        days=int((now-start)//86400)
        if days>0:
            lost=days*2
            affection=max(0,affection-lost)
    if gain or lost:
        con.execute(
            "UPDATE pets SET energy=?,energy_at=?,affection=?,decay_at=? WHERE user_id=? AND species=?",
            (energy,energy_at,affection,now if lost else data["decay_at"],user_id,species)
        )
        data.update({"energy":energy,"energy_at":energy_at,"affection":affection,"decay_at":now if lost else data["decay_at"]})
    return data

def active(con,user_id,now=None):
    touch(con,user_id)
    row=con.execute("SELECT active FROM pet_users WHERE user_id=?",(user_id,)).fetchone()
    species=row["active"] if row else None
    if species:
        pet=fresh(con,user_id,species,now)
        if pet:
            return pet
    first=con.execute("SELECT species FROM pets WHERE user_id=? ORDER BY adopted_at LIMIT 1",(user_id,)).fetchone()
    if first:
        con.execute("UPDATE pet_users SET active=? WHERE user_id=?",(first[0],user_id))
        return fresh(con,user_id,first[0],now)
    return None

def adopt(
    user_id,
    species,
    guild_id
):
    if species not in SPECIES:
        return {
            "ok":False,
            "reason":"species"
        }

    now=time.time()

    info=SPECIES[
        species
    ]

    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        touch(
            con,
            user_id
        )

        if con.execute(
            """SELECT 1
            FROM pets
            WHERE user_id=?
            AND species=?""",
            (
                user_id,
                species
            )
        ).fetchone():
            return {
                "ok":False,
                "reason":"owned"
            }

        if info[
            "tier"
        ]=="rosarium":
            progress=rosariumprogress(
                con,
                user_id
            )

            if not progress[
                "encountered"
            ]:
                return {
                    "ok":False,
                    "reason":"rosarium",
                    **progress
                }

        else:
            high=highest(
                con,
                user_id
            )

            if high<int(
                info[
                    "unlock"
                ]
            ):
                return {
                    "ok":False,
                    "reason":"locked",
                    "level":
                        info[
                            "unlock"
                        ],
                    "high":high
                }

        cost=int(
            info[
                "cost"
            ]
        )

        if cost:
            con.execute(
                """INSERT OR IGNORE INTO wallets(
                    guild_id,user_id
                ) VALUES(?,?)""",
                (
                    guild_id,
                    user_id
                )
            )

            roses=int(
                con.execute(
                    """SELECT roses
                    FROM wallets
                    WHERE guild_id=?
                    AND user_id=?""",
                    (
                        guild_id,
                        user_id
                    )
                ).fetchone()[0]
            )

            if roses<cost:
                return {
                    "ok":False,
                    "reason":"broke",
                    "need":
                        cost-roses,
                    "cost":cost
                }

            con.execute(
                """UPDATE wallets
                SET roses=roses-?
                WHERE guild_id=?
                AND user_id=?""",
                (
                    cost,
                    guild_id,
                    user_id
                )
            )

        con.execute(
            """INSERT INTO pets(
                user_id,
                species,
                name,
                energy_at,
                adopted_at,
                last_care,
                decay_at
            ) VALUES(?,?,?,?,?,?,?)""",
            (
                user_id,
                species,
                info[
                    "name"
                ],
                now,
                now,
                now,
                now
            )
        )

        con.execute(
            """UPDATE pet_users
            SET active=?,
                spent=spent+?
            WHERE user_id=?""",
            (
                species,
                cost,
                user_id
            )
        )

        if info[
            "tier"
        ]=="rosarium":
            con.execute(
                """INSERT INTO pet_rosarium(
                    user_id,
                    butterfly_encountered_at,
                    butterfly_adopted_at
                ) VALUES(?,?,?)
                ON CONFLICT(user_id)
                DO UPDATE SET
                    butterfly_adopted_at=
                        excluded.butterfly_adopted_at""",
                (
                    user_id,
                    now,
                    now
                )
            )

    return {
        "ok":True,
        "species":species,
        "cost":cost
    }

def switch(user_id,species):
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        touch(con,user_id)
        if not con.execute("SELECT 1 FROM pets WHERE user_id=? AND species=?",(user_id,species)).fetchone():
            return False
        con.execute("UPDATE pet_users SET active=? WHERE user_id=?",(species,user_id))
    return True

def rename(user_id,name,guild_id):
    name=clean(name)
    if name is None:
        return {"ok":False,"reason":"name"}
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        pet=active(con,user_id)
        if pet is None:
            return {"ok":False,"reason":"none"}
        cost=RENAME_COST if pet["named"] else 0
        if cost:
            con.execute("INSERT OR IGNORE INTO wallets(guild_id,user_id) VALUES(?,?)",(guild_id,user_id))
            roses=con.execute("SELECT roses FROM wallets WHERE guild_id=? AND user_id=?",(guild_id,user_id)).fetchone()[0]
            if roses<cost:
                return {"ok":False,"reason":"broke","need":cost-roses,"cost":cost}
            con.execute("UPDATE wallets SET roses=roses-? WHERE guild_id=? AND user_id=?",(cost,guild_id,user_id))
            con.execute("UPDATE pet_users SET spent=spent+? WHERE user_id=?",(cost,user_id))
        con.execute("UPDATE pets SET name=?,named=1 WHERE user_id=? AND species=?",(name,user_id,pet["species"]))
    return {"ok":True,"name":name,"cost":cost}

def do_feed(user_id,guild_id):
    now=time.time()
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        pet=active(con,user_id,now)
        if pet is None:
            return {"ok":False,"reason":"none"}
        ready=pet["last_feed"]+FEED_CD
        if now<ready:
            return {"ok":False,"reason":"cooldown","ready":ready}
        con.execute("INSERT OR IGNORE INTO wallets(guild_id,user_id) VALUES(?,?)",(guild_id,user_id))
        roses=con.execute("SELECT roses FROM wallets WHERE guild_id=? AND user_id=?",(guild_id,user_id)).fetchone()[0]
        if roses<FEED_COST:
            return {"ok":False,"reason":"broke","need":FEED_COST-roses,"cost":FEED_COST}
        level,xp,gained=levelup(pet["level"],pet["xp"],12)
        energy=min(100,pet["energy"]+35)
        affection=min(100,pet["affection"]+5)
        con.execute("UPDATE wallets SET roses=roses-? WHERE guild_id=? AND user_id=?",(FEED_COST,guild_id,user_id))
        con.execute("UPDATE pet_users SET spent=spent+? WHERE user_id=?",(FEED_COST,user_id))
        con.execute("""UPDATE pets SET level=?,xp=?,energy=?,energy_at=?,affection=?,last_care=?,decay_at=?,last_feed=?,feeds=feeds+1
            WHERE user_id=? AND species=?""",(level,xp,energy,now,affection,now,now,now,user_id,pet["species"]))
    return {"ok":True,"pet":pet,"level":level,"gained":gained,"cost":FEED_COST}

def do_play(user_id,guild_id):
    now=time.time()
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        pet=active(con,user_id,now)
        if pet is None:
            return {"ok":False,"reason":"none"}
        ready=pet["last_play"]+PLAY_CD
        if now<ready:
            return {"ok":False,"reason":"cooldown","ready":ready}
        if pet["energy"]<10:
            return {"ok":False,"reason":"energy"}
        con.execute("INSERT OR IGNORE INTO wallets(guild_id,user_id) VALUES(?,?)",(guild_id,user_id))
        roses=con.execute("SELECT roses FROM wallets WHERE guild_id=? AND user_id=?",(guild_id,user_id)).fetchone()[0]
        if roses<PLAY_COST:
            return {"ok":False,"reason":"broke","need":PLAY_COST-roses,"cost":PLAY_COST}
        level,xp,gained=levelup(pet["level"],pet["xp"],15)
        affection=min(100,pet["affection"]+4)
        con.execute("UPDATE wallets SET roses=roses-? WHERE guild_id=? AND user_id=?",(PLAY_COST,guild_id,user_id))
        con.execute("UPDATE pet_users SET spent=spent+? WHERE user_id=?",(PLAY_COST,user_id))
        con.execute("""UPDATE pets SET level=?,xp=?,energy=?,energy_at=?,affection=?,last_care=?,decay_at=?,last_play=?,plays=plays+1
            WHERE user_id=? AND species=?""",(level,xp,pet["energy"]-10,now,affection,now,now,now,user_id,pet["species"]))
    return {"ok":True,"pet":pet,"level":level,"gained":gained,"cost":PLAY_COST}

def explore_roll():
    n=secrets.randbelow(10000)
    for chance,value,label in EXPLORE:
        if n<chance:
            return value,label
        n-=chance
    raise RuntimeError("pet explore odds died")

def do_explore(user_id,guild_id):
    now=time.time()
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        pet=active(con,user_id,now)
        if pet is None:
            return {"ok":False,"reason":"none"}
        ready=pet["last_explore"]+EXPLORE_CD
        if now<ready:
            return {"ok":False,"reason":"cooldown","ready":ready}
        if pet["energy"]<15:
            return {"ok":False,"reason":"energy"}
        base,label=explore_roll()
        bonus=(pet["level"]-1)*20//(MAX_LEVEL-1)
        reward=base*(100+bonus)//100
        level,xp,gained=levelup(pet["level"],pet["xp"],12)
        affection=min(100,pet["affection"]+1)
        discovery=None
        new=False
        if secrets.randbelow(10000)<800:
            discovery=secrets.choice(SPECIES[pet["species"]]["finds"])
            cur=con.execute("INSERT OR IGNORE INTO pet_finds(user_id,species,item,found_at) VALUES(?,?,?,?)",(user_id,pet["species"],discovery,now))
            new=cur.rowcount==1
        incident=None
        if secrets.randbelow(10000)<250:
            incident=secrets.choice(SPECIES[pet["species"]]["incidents"])
        con.execute("INSERT OR IGNORE INTO wallets(guild_id,user_id) VALUES(?,?)",(guild_id,user_id))
        con.execute("UPDATE wallets SET roses=roses+? WHERE guild_id=? AND user_id=?",(reward,guild_id,user_id))
        con.execute("UPDATE pet_users SET earned=earned+? WHERE user_id=?",(reward,user_id))
        con.execute("""UPDATE pets SET level=?,xp=?,energy=?,energy_at=?,affection=?,last_care=?,decay_at=?,last_explore=?,explores=explores+1,earned=earned+?
            WHERE user_id=? AND species=?""",(level,xp,pet["energy"]-15,now,affection,now,now,now,reward,user_id,pet["species"]))
    return {"ok":True,"pet":pet,"level":level,"gained":gained,"reward":reward,"label":label,"discovery":discovery,"new":new,"incident":incident}

def finds(user_id,species):
    with connect() as con:
        rows=con.execute("SELECT item FROM pet_finds WHERE user_id=? AND species=? ORDER BY found_at",(user_id,species)).fetchall()
    return [row[0] for row in rows]

def disease(user_id):
    try:
        with connect() as con:
            row=con.execute("SELECT disease FROM pluck_users WHERE user_id=?",(user_id,)).fetchone()
        return row[0] if row else None
    except sqlite3.OperationalError:
        return None

def mood(pet):
    if pet["species"]=="rosaerie":
        sick=disease(
            pet[
                "user_id"
            ]
        )

        if sick=="roseola":
            return "fascinated by your roseola"

        if sick=="rosacea":
            return "delighted by your rosacea"

    moods=SPECIES[
        pet[
            "species"
        ]
    ][
        "moods"
    ]

    key=(
        f"{game.day().isoformat()}:"
        f"{pet['user_id']}:"
        f"{pet['species']}"
    )

    n=int.from_bytes(
        hashlib.sha256(
            key.encode()
        ).digest()[:4],
        "big"
    )

    return moods[
        n%len(
            moods
        )
    ]

def ready(last,cd):
    when=last+cd
    return "ready" if time.time()>=when else f"<t:{int(when)}:R>"

def panel(
    user_id,
    note=None
):
    with connect() as con:
        pet=active(
            con,
            user_id
        )

        count=con.execute(
            """SELECT COUNT(*)
            FROM pets
            WHERE user_id=?""",
            (
                user_id,
            )
        ).fetchone()[0]

        if pet is None:
            high=highest(
                con,
                user_id
            )

            rosarium=rosariumprogress(
                con,
                user_id
            )

            lines=[]

            for tier in TIER_ORDER:
                lines.append(
                    f"**{TIER_LABELS[tier]}**"
                )

                for key in petcatalog.BY_TIER[
                    tier
                ]:
                    info=SPECIES[
                        key
                    ]

                    can=available(
                        con,
                        user_id,
                        key
                    )

                    mark=(
                        ""
                        if can
                        else "🔒 "
                    )

                    if tier=="rosarium":
                        if rosarium[
                            "encountered"
                        ]:
                            status=(
                                "**waiting in your garden**"
                            )

                        else:
                            status=(
                                f"**{rosarium['owned']}/"
                                f"{petcatalog.ROSARIUM_NORMALS} pets** "
                                f"• **{rosarium['garden_level']:,}/"
                                f"{petcatalog.ROSARIUM_GARDEN_LEVEL:,} garden**"
                            )

                    elif can:
                        status=(
                            f"**{info['cost']:,} roses "
                            f"{rosieemoji.ROSE}**"
                        )

                    else:
                        status=(
                            f"lvl **{info['unlock']}** "
                            f"⊹ **{info['cost']:,} roses "
                            f"{rosieemoji.ROSE}**"
                        )

                    lines.append(
                        f"{mark}{info['emoji']} "
                        f"**{info['name']}** "
                        f"⊹ {status}"
                    )


                lines.append(
                    ""
                )


            return discord.Embed(
                title="🐾 pets",
                description="\n".join(lines).rstrip(),
                color=discord.Color.dark_red()
            )

    info=SPECIES[
        pet[
            "species"
        ]
    ]

    got=finds(
        user_id,
        pet[
            "species"
        ]
    )

    xp=(
        "MAX"
        if pet[
            "level"
        ]>=MAX_LEVEL
        else (
            f"{pet['xp']:,} / "
            f"{need(pet['level']):,}"
        )
    )

    body=[]

    if note:
        body.extend((
            note,
            ""
        ))

    body.extend((
        f"{info['emoji']} **{shown(pet['name'])}**",
        (
            f"{info['name']} ⊹ "
            f"**{TIER_LABELS[info['tier']]}** "
            f"⊹ lvl **{pet['level']}**"
        ),
        "",
        f"mood ⊹ **{mood(pet)}**",
        f"affection ⊹ **{pet['affection']}%**",
        f"energy ⊹ **{pet['energy']}%**",
        f"xp ⊹ **{xp}**",
        "",
        "**care**",
        (
            f"🍓 feed ⊹ "
            f"{ready(pet['last_feed'],FEED_CD)} "
            f"⊹ {FEED_COST} roses "
            f"{rosieemoji.ROSE}"
        ),
        (
            f"🎀 play ⊹ "
            f"{ready(pet['last_play'],PLAY_CD)} "
            f"⊹ {PLAY_COST} roses "
            f"{rosieemoji.ROSE}"
        ),
        (
            f"🌿 explore ⊹ "
            f"{ready(pet['last_explore'],EXPLORE_CD)}"
        ),
        "",
        (
            f"earned ⊹ "
            f"**{pet['earned']:,} roses "
            f"{rosieemoji.ROSE}**"
        ),
        (
            f"finds ⊹ "
            f"**{len(got)} / "
            f"{len(info['finds'])}**"
        ),
        (
            f"pets owned ⊹ "
            f"**{count} / "
            f"{len(SPECIES)}**"
        )
    ))

    return discord.Embed(
        title="🐾 pet",
        description="\n".join(
            body
        ),
        color=discord.Color.dark_red()
    )

def perks_embed(user_id):
    from core import petbuff

    lines=[]
    active=petbuff.get(user_id)
    if active:
        lines.extend((
            f"**active perk** ⊹ {active['emoji']} **{active['label']}**",
            f"expires ⊹ <t:{int(active['expires_at'])}:R>",
            ""
        ))

    for tier in TIER_ORDER:
        lines.append(f"**{TIER_LABELS[tier]}**")
        for key in petcatalog.BY_TIER[tier]:
            info=SPECIES[key]
            lines.append(
                f"{info['emoji']} **{info['name']}** "
                f"⊹ **{info['buff']['label']}** ⊹ {info['buff']['text']}"
            )
        lines.append("")

    lines.append("perks activate for **3h after play**")
    return discord.Embed(
        title="❔ pet perks",
        description="\n".join(lines),
        color=discord.Color.dark_red()
    )

def roster(
    user_id
):
    with connect() as con:
        touch(
            con,
            user_id
        )

        pets=owned(
            con,
            user_id
        )

        high=highest(
            con,
            user_id
        )

        active_row=con.execute(
            """SELECT active
            FROM pet_users
            WHERE user_id=?""",
            (
                user_id,
            )
        ).fetchone()

        current=(
            active_row[0]
            if active_row
            else None
        )

        rosarium=rosariumprogress(
            con,
            user_id
        )

    lines=[]

    for tier in TIER_ORDER:
        if lines:
            lines.append(
                ""
            )

        lines.append(
            f"**{TIER_LABELS[tier]}**"
        )

        for key in petcatalog.BY_TIER[
            tier
        ]:
            info=SPECIES[
                key
            ]

            if key in pets:
                mark=(
                    "✦"
                    if key==current
                    else "✓"
                )

                lines.append(
                    f"{mark} {info['emoji']} "
                    f"**{info['name']}** "
                    f"⊹ lvl {pets[key]['level']}"
                )

            elif tier=="rosarium":
                if rosarium[
                    "encountered"
                ]:
                    lines.append(
                        f"◻️ {info['emoji']} "
                        f"**{info['name']}** "
                        "⊹ waiting in your garden"
                    )

                elif rosarium[
                    "eligible"
                ]:
                    lines.append(
                        f"🔒 {info['emoji']} "
                        f"**{info['name']}** "
                        "⊹ garden ready "
                        "• 0.1% / harvested plant"
                    )

                else:
                    lines.append(
                        f"🔒 {info['emoji']} "
                        f"**{info['name']}** "
                        f"⊹ {rosarium['owned']}/"
                        f"{petcatalog.ROSARIUM_NORMALS} pets "
                        f"• {rosarium['garden_level']:,}/"
                        f"{petcatalog.ROSARIUM_GARDEN_LEVEL:,} garden"
                    )

            elif high>=int(
                info[
                    "unlock"
                ]
            ):
                lines.append(
                    f"◻️ {info['emoji']} "
                    f"**{info['name']}** "
                    f"⊹ {info['cost']:,} "
                    f"{rosieemoji.ROSE}"
                )

            else:
                lines.append(
                    f"🔒 {info['emoji']} "
                    f"**{info['name']}** "
                    f"⊹ lvl {info['unlock']}"
                )

    lines.extend((
        "",
        f"highest pet level ⊹ **{high}**"
    ))

    return discord.Embed(
        title="🐾 your pets",
        description="\n".join(
            lines
        ),
        color=discord.Color.dark_red()
    )

def options(
    user_id
):
    with connect() as con:
        pets=owned(
            con,
            user_id
        )

        current=con.execute(
            """SELECT active
            FROM pet_users
            WHERE user_id=?""",
            (
                user_id,
            )
        ).fetchone()

        current=(
            current[0]
            if current
            else None
        )

        out=[]

        for key,info in SPECIES.items():
            if key in pets:
                desc=(
                    f"{TIER_LABELS[info['tier']]} ⊹ "
                    f"lvl {pets[key]['level']} ⊹ "
                    +(
                        "active"
                        if key==current
                        else "switch"
                    )
                )

            elif available(
                con,
                user_id,
                key
            ):
                desc=(
                    "rosarium ⊹ found ⊹ adopt"
                    if info[
                        "tier"
                    ]=="rosarium"
                    else (
                        f"{TIER_LABELS[info['tier']]} ⊹ "
                        f"adopt ⊹ "
                        f"{info['cost']:,} roses"
                    )
                )

            else:
                continue

            out.append(
                discord.SelectOption(
                    label=info[
                        "name"
                    ],
                    value=key,
                    emoji=info[
                        "emoji"
                    ],
                    description=desc[
                        :100
                    ]
                )
            )

    return out

def action_note(result,kind):
    pet=result["pet"]
    info=SPECIES[pet["species"]]
    name=shown(pet["name"])
    if kind=="feed":
        text=f"{info['emoji']} **{name}** {secrets.choice(info['feed'])}\n-{result['cost']:,} roses {rosieemoji.ROSE} • +12 xp"
    elif kind=="play":
        text=f"{info['emoji']} **{name}** {secrets.choice(info['play'])}\n-{result['cost']:,} roses {rosieemoji.ROSE} • +15 xp"
    else:
        text=(f"{info['emoji']} **{name}** {secrets.choice(info['explore'])}\n{result['label']} ⊹ **+{result['reward']:,} roses {rosieemoji.ROSE}** • +12 xp")
        if result["discovery"]:
            if result["new"]:
                text+=f"\n\n✦ **new discovery**\n`{result['discovery']}`"
            else:
                text+=f"\n\nfound another `{result['discovery']}`"
        if result["incident"]:
            text+=f"\n\n**something is wrong**\n{result['incident']}"
    if result["gained"]:
        text+=f"\n\n✦ **level up** ⊹ lvl {result['level']}"
    return text

async def error(it,result):
    reason=result["reason"]
    if reason=="cooldown":
        text=f"not yet babe\nready ⊹ <t:{int(result['ready'])}:R>"
    elif reason=="broke":
        text=f"you need **{result['need']:,} more roses {rosieemoji.ROSE}**"
    elif reason=="energy":
        text="too tired rn\nfeed them or let their energy recover"
    else:
        text="you need a pet first"
    await it.response.send_message(text,ephemeral=True)

class RenameModal(discord.ui.Modal,title="rename pet"):
    field=discord.ui.TextInput(label="new name",min_length=1,max_length=20,placeholder="Morrow")

    def __init__(self,user_id,guild_id):
        super().__init__()
        self.user_id=user_id
        self.guild_id=guild_id

    async def on_submit(self,it:discord.Interaction):
        result=rename(self.user_id,str(self.field),self.guild_id)
        if not result["ok"]:
            if result["reason"]=="broke":
                text=f"you need **{result['need']:,} more roses {rosieemoji.ROSE}**"
            else:
                text="that name is not happening"
            await it.response.send_message(text,ephemeral=True)
            return
        cost="first name is free" if result["cost"]==0 else f"-{result['cost']:,} roses {rosieemoji.ROSE}"
        await it.response.send_message(f"renamed ⊹ **{shown(result['name'])}**\n{cost}",ephemeral=True)

class PetSelect(discord.ui.Select):
    def __init__(
        self,
        user_id
    ):
        super().__init__(
            placeholder="pick a pet",
            options=options(
                user_id
            )
        )

    async def callback(
        self,
        it:discord.Interaction
    ):
        species=self.values[
            0
        ]

        user_id=self.view.user_id

        with connect() as con:
            pets=owned(
                con,
                user_id
            )

            can=available(
                con,
                user_id,
                species
            )

            progress=(
                rosariumprogress(
                    con,
                    user_id
                )
                if SPECIES[
                    species
                ][
                    "tier"
                ]=="rosarium"
                else None
            )

        info=SPECIES[
            species
        ]

        if species in pets:
            switch(
                user_id,
                species
            )

            await it.response.edit_message(
                embed=roster(
                    user_id
                ),
                view=ManageView(
                    user_id,
                    self.view.guild_id
                )
            )
            return

        if not can:
            if info[
                "tier"
            ]=="rosarium":
                text=(
                    "rosarium locked ⊹ "
                    f"{progress['owned']}/"
                    f"{petcatalog.ROSARIUM_NORMALS} pets "
                    f"• {progress['garden_level']:,}/"
                    f"{petcatalog.ROSARIUM_GARDEN_LEVEL:,} garden"
                )

                if progress[
                    "eligible"
                ]:
                    text=(
                        "the garden is ready ⊹ "
                        "0.1% chance per harvested plant"
                    )

            else:
                text=(
                    "locked ⊹ raise any pet to "
                    f"**lvl {info['unlock']}** first"
                )

            await it.response.send_message(
                text,
                ephemeral=True
            )
            return

        cost=(
            "free"
            if not info[
                "cost"
            ]
            else (
                f"{info['cost']:,} roses "
                f"{rosieemoji.ROSE}"
            )
        )

        embed=discord.Embed(
            title=(
                f"{info['emoji']} "
                f"adopt {info['name']}"
            ),
            description=(
                f"tier ⊹ **{TIER_LABELS[info['tier']]}**\n"
                f"cost ⊹ **{cost}**\n"
                f"requires ⊹ "
                f"**{requirement(info)}**\n"
                f"perk ⊹ "
                f"**{info['buff']['label']}** "
                f"• {info['buff']['text']}\n\n"
                "this pet becomes your active pet"
            ),
            color=discord.Color.dark_red()
        )

        await it.response.edit_message(
            embed=embed,
            view=AdoptView(
                user_id,
                species,
                self.view.guild_id
            )
        )

class ManageView(discord.ui.View):
    def __init__(self,user_id,guild_id):
        super().__init__(timeout=180)
        self.user_id=user_id
        self.guild_id=guild_id
        self.add_item(PetSelect(user_id))
        with connect() as con:
            self.rename.disabled=active(con,user_id) is None

    @discord.ui.button(emoji="✏️",style=discord.ButtonStyle.secondary,row=1)
    async def rename(self,it:discord.Interaction,button:discord.ui.Button):
        await it.response.send_modal(RenameModal(self.user_id,self.guild_id))

    async def interaction_check(self,it:discord.Interaction):
        if it.user.id==self.user_id:
            return True
        await it.response.send_message("make ur own /pet",ephemeral=True)
        return False

class AdoptView(discord.ui.View):
    def __init__(
        self,
        user_id,
        species,
        guild_id
    ):
        super().__init__(
            timeout=120
        )

        self.user_id=user_id
        self.species=species
        self.guild_id=guild_id

    async def interaction_check(
        self,
        it:discord.Interaction
    ):
        if it.user.id==self.user_id:
            return True

        await it.response.send_message(
            "make ur own /pet",
            ephemeral=True
        )

        return False

    @discord.ui.button(
        emoji=rosieemoji.ROSE,
        style=discord.ButtonStyle.danger
    )
    async def confirm(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        result=adopt(
            self.user_id,
            self.species,
            self.guild_id
        )

        if not result[
            "ok"
        ]:
            reason=result[
                "reason"
            ]

            if reason=="broke":
                text=(
                    f"you need "
                    f"**{result['need']:,} more roses "
                    f"{rosieemoji.ROSE}**"
                )

            elif reason=="locked":
                text=(
                    "locked until pet lvl "
                    f"**{result['level']}**"
                )

            elif reason=="rosarium":
                if result.get(
                    "eligible"
                ):
                    text=(
                        "the garden is ready ⊹ "
                        "keep harvesting"
                    )
                else:
                    text=(
                        "rosarium locked ⊹ "
                        f"{result['owned']}/"
                        f"{petcatalog.ROSARIUM_NORMALS} pets "
                        f"• {result['garden_level']:,}/"
                        f"{petcatalog.ROSARIUM_GARDEN_LEVEL:,} garden"
                    )

            else:
                text="you already own that one"

            await it.response.send_message(
                text,
                ephemeral=True
            )
            return

        info=SPECIES[
            self.species
        ]

        cost=(
            "free"
            if not result[
                "cost"
            ]
            else (
                f"-{result['cost']:,} roses "
                f"{rosieemoji.ROSE}"
            )
        )

        description=(
            f"**{info['name']}** is yours\n"
            f"{cost}\n\n"
            "first rename is free"
        )

        if info[
            "tier"
        ]=="rosarium":
            description=(
                "**butterfly** followed you home.\n"
                "rosarium pet unlocked ✦\n\n"
                "first rename is free"
            )

        await it.response.edit_message(
            embed=discord.Embed(
                title=(
                    f"{info['emoji']} adopted"
                ),
                description=description,
                color=discord.Color.dark_red()
            ),
            view=ManageView(
                self.user_id,
                self.guild_id
            )
        )

    @discord.ui.button(
        label="back",
        style=discord.ButtonStyle.secondary
    )
    async def back(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        await it.response.edit_message(
            embed=roster(
                self.user_id
            ),
            view=ManageView(
                self.user_id,
                self.guild_id
            )
        )

class PetView(discord.ui.View):
    def __init__(self,user_id,guild_id):
        super().__init__(timeout=300)
        self.user_id=user_id
        self.guild_id=guild_id
        with connect() as con:
            has=active(con,user_id) is not None
        self.feed.disabled=not has
        self.play.disabled=not has
        self.explore.disabled=not has
        self.discoveries.disabled=not has

    async def interaction_check(self,it:discord.Interaction):
        if it.user.id==self.user_id:
            return True
        await it.response.send_message("make ur own /pet",ephemeral=True)
        return False

    @discord.ui.button(emoji="🍓",style=discord.ButtonStyle.secondary,row=0)
    async def feed(self,it:discord.Interaction,button:discord.ui.Button):
        result=do_feed(self.user_id,self.guild_id)
        if not result["ok"]:
            await error(it,result)
            return
        await it.response.edit_message(embed=panel(self.user_id,action_note(result,"feed")),view=PetView(self.user_id,self.guild_id))

    @discord.ui.button(emoji="🎀",style=discord.ButtonStyle.secondary,row=0)
    async def play(self,it:discord.Interaction,button:discord.ui.Button):
        result=do_play(self.user_id,self.guild_id)
        if not result["ok"]:
            await error(it,result)
            return
        await it.response.edit_message(embed=panel(self.user_id,action_note(result,"play")),view=PetView(self.user_id,self.guild_id))

    @discord.ui.button(emoji="🌿",style=discord.ButtonStyle.success,row=0)
    async def explore(self,it:discord.Interaction,button:discord.ui.Button):
        result=do_explore(self.user_id,self.guild_id)
        if not result["ok"]:
            await error(it,result)
            return
        await it.response.edit_message(embed=panel(self.user_id,action_note(result,"explore")),view=PetView(self.user_id,self.guild_id))

    @discord.ui.button(emoji="🐾",style=discord.ButtonStyle.secondary,row=1)
    async def pets(self,it:discord.Interaction,button:discord.ui.Button):
        await it.response.send_message(embed=roster(self.user_id),view=ManageView(self.user_id,self.guild_id),ephemeral=True)

    @discord.ui.button(emoji="❔",style=discord.ButtonStyle.secondary,row=1)
    async def perks(self,it:discord.Interaction,button:discord.ui.Button):
        await it.response.send_message(embed=perks_embed(self.user_id),ephemeral=True)

    @discord.ui.button(emoji="✨",style=discord.ButtonStyle.secondary,row=1)
    async def discoveries(self,it:discord.Interaction,button:discord.ui.Button):
        with connect() as con:
            pet=active(con,self.user_id)
        if pet is None:
            await it.response.send_message("you need a pet first",ephemeral=True)
            return
        info=SPECIES[pet["species"]]
        got=set(finds(self.user_id,pet["species"]))
        lines=[f"{'✦' if item in got else '◻️'} {item if item in got else '???'}" for item in info["finds"]]
        await it.response.send_message(
            embed=discord.Embed(
                title=f"{info['emoji']} {shown(pet['name'])}'s finds",
                description="\n".join(lines),
                color=discord.Color.dark_red()
            ),
            ephemeral=True
        )

class Pet(commands.Cog):
    @app_commands.command(
        name="pet",
        description="take care of your little problem"
    )
    @app_commands.guild_only()
    async def pet(
        self,
        it:discord.Interaction
    ):
        game.touch(
            it.user.id
        )

        notice=morph_notice(
            it.user.id,
            it.guild_id
        )

        await it.response.send_message(
            embed=panel(
                it.user.id
            ),
            view=PetView(
                it.user.id,
                it.guild_id
            )
        )

        if notice:
            try:
                await it.followup.send(
                    embed=morphembed(
                        notice
                    ),
                    ephemeral=True
                )

                mark_morph_noticed(
                    it.user.id
                )

            except discord.HTTPException:
                pass

async def setup(bot):
    init()
    await bot.add_cog(Pet())
