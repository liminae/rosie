import importlib
import secrets
import sqlite3
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from core import database
from core import brewing

ET=ZoneInfo("America/New_York")
PASS_COST=3
TIER_XP=100
MAX_XP=1000

HALLOW_START=datetime(
    2026,
    10,
    1,
    tzinfo=ET
)

HALLOW_END=datetime(
    2026,
    11,
    1,
    tzinfo=ET
)

MONTHS={
    1:"pale dawn",
    2:"thornheart",
    3:"first bloom",
    4:"rainspell",
    5:"wildrose",
    6:"midsummer",
    7:"sunfall",
    8:"overgrowth",
    9:"harvest moon",
    10:"nightshade",
    11:"black harvest",
    12:"frostfall"
}

FREE={
    1:500,
    2:750,
    3:750,
    4:1000,
    5:1000,
    6:1250,
    7:1250,
    8:1500,
    9:1750,
    10:2250
}

PAID={
    1:2000,
    2:2000,
    3:2500,
    4:2500,
    5:2500,
    6:3000,
    7:3000,
    8:3500,
    9:4000,
    10:5000
}

COMMAND_XP={
    "daily":(5,5),
    "pluck":(1,8),
    "garden":(1,4),
    "forage":(1,6),
    "brew":(1,4),
    "quests":(2,4),
    "pet":(1,4),
    "campaign":(2,10),
    "boss":(3,6),
    "scratch":(2,2),
    "relic":(2,4),
    "reaper":(2,4),
    "rune":(2,4),
    "sin":(2,4),
    "parlor":(1,2)
}

INGREDIENTS={
    "pumpkin":{
        "name":"pumpkin",
        "plural":"pumpkins",
        "emoji":"🎃"
    },
    "web":{
        "name":"web",
        "plural":"webs",
        "emoji":"🕸️"
    },
    "bone":{
        "name":"bone",
        "plural":"bones",
        "emoji":"🦴"
    },
    "wax":{
        "name":"wax",
        "plural":"wax",
        "emoji":"🕯️"
    }
}

RECIPES={
    "jack":{
        "name":"jack-o'-tonic",
        "emoji":"🎃",
        "cost":{
            "pumpkin":4,
            "wax":2
        },
        "text":"+30% GXP on your next 8 harvested plants"
    },
    "spider":{
        "name":"spider silk",
        "emoji":"🕸️",
        "cost":{
            "web":4,
            "wax":2
        },
        "text":"next 5 forage actions find +1 ingredient"
    },
    "marrow":{
        "name":"marrow brew",
        "emoji":"🦴",
        "cost":{
            "bone":4,
            "pumpkin":2
        },
        "text":"+10 season XP • max 2/day"
    },
    "witchlight":{
        "name":"witchlight",
        "emoji":"🕯️",
        "cost":{
            "wax":4,
            "web":2,
            "bone":1
        },
        "text":"save one bad adventure"
    }
}

PLACES={
    "greenhouse":(
        "the greenhouse",
        "🌿",
        (
            (45,"item","pumpkin",2),
            (25,"item","web",1),
            (20,"item","wax",1),
            (10,"roses","roses",150)
        )
    ),
    "graveyard":(
        "the graveyard",
        "🪦",
        (
            (50,"item","bone",2),
            (25,"item","wax",1),
            (15,"item","web",1),
            (10,"nothing","nothing",0)
        )
    ),
    "manor":(
        "the manor",
        "🏚️",
        (
            (35,"item","wax",2),
            (30,"item","web",2),
            (20,"item","pumpkin",2),
            (10,"roses","roses",250),
            (5,"nothing","nothing",0)
        )
    ),
    "crypt":(
        "the crypt",
        "⚰️",
        (
            (40,"item","bone",3),
            (25,"item","wax",2),
            (20,"item","web",2),
            (10,"roses","roses",250),
            (5,"nothing","nothing",0)
        )
    ),
    "woods":(
        "the woods",
        "🌲",
        (
            (45,"item","web",2),
            (30,"item","pumpkin",2),
            (15,"item","bone",1),
            (10,"nothing","nothing",0)
        )
    ),
    "chapel":(
        "the chapel",
        "⛪",
        (
            (45,"item","wax",2),
            (30,"item","bone",1),
            (15,"item","pumpkin",1),
            (10,"roses","roses",150)
        )
    )
}

INSTALLED=False

def connect():
    con=sqlite3.connect(
        database.FILE,
        timeout=10
    )
    con.row_factory=sqlite3.Row
    return con

def preview():
    return {
        "id":"2026-10-witching-hour",
        "name":"witching hour",
        "number":1,
        "start":HALLOW_START,
        "end":HALLOW_END,
        "halloween":True
    }

def current(now=None):
    now=now or datetime.now(
        ET
    )

    if (
        HALLOW_START
        <=now
        <HALLOW_END
    ):
        return preview()

    if now<HALLOW_START:
        return None

    if now.month==12:
        end=datetime(
            now.year+1,
            1,
            1,
            tzinfo=ET
        )
    else:
        end=datetime(
            now.year,
            now.month+1,
            1,
            tzinfo=ET
        )

    number=(
        now.year*12
        +now.month
        -(2026*12+10)
        +1
    )

    return {
        "id":(
            f"{now.year}-"
            f"{now.month:02d}-"
            f"{MONTHS[now.month].replace(' ','-')}"
        ),
        "name":MONTHS[
            now.month
        ],
        "number":number,
        "start":datetime(
            now.year,
            now.month,
            1,
            tzinfo=ET
        ),
        "end":end,
        "halloween":False
    }

def init():
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS season_users(
            user_id INTEGER NOT NULL,
            season TEXT NOT NULL,
            xp INTEGER NOT NULL DEFAULT 0,
            paid INTEGER NOT NULL DEFAULT 0,
            paid_guild_id INTEGER,
            PRIMARY KEY(user_id,season)
        )""")

        usercols={row["name"] for row in con.execute("PRAGMA table_info(season_users)")}
        if "paid_guild_id" not in usercols:
            con.execute("ALTER TABLE season_users ADD COLUMN paid_guild_id INTEGER")

        con.execute("""CREATE TABLE IF NOT EXISTS season_claims(
            user_id INTEGER NOT NULL,
            season TEXT NOT NULL,
            track TEXT NOT NULL,
            tier INTEGER NOT NULL,
            claimed_at REAL NOT NULL,
            PRIMARY KEY(user_id,season,track,tier)
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS season_daily(
            user_id INTEGER NOT NULL,
            season TEXT NOT NULL,
            day TEXT NOT NULL,
            key TEXT NOT NULL,
            amount INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id,season,day,key)
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS season_messages(
            user_id INTEGER NOT NULL,
            season TEXT NOT NULL,
            last_at REAL NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id,season)
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS season_items(
            user_id INTEGER NOT NULL,
            season TEXT NOT NULL,
            item TEXT NOT NULL,
            amount INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id,season,item)
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS season_bottles(
            user_id INTEGER NOT NULL,
            season TEXT NOT NULL,
            potion TEXT NOT NULL,
            amount INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id,season,potion)
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS season_effects(
            user_id INTEGER NOT NULL,
            season TEXT NOT NULL,
            effect TEXT NOT NULL,
            amount INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id,season,effect)
        )""")

def migrateguild(guild_id):
    with connect() as con:
        con.execute("UPDATE season_users SET paid_guild_id=? WHERE paid=1 AND paid_guild_id IS NULL",(guild_id,))

def today():
    return datetime.now(
        ET
    ).date().isoformat()

def touch(
    con,
    user_id,
    sid
):
    con.execute(
        """INSERT OR IGNORE INTO season_users(
            user_id,season
        ) VALUES(?,?)""",
        (
            user_id,
            sid
        )
    )

def allowance(
    con,
    user_id,
    sid,
    key,
    amount,
    cap
):
    row=con.execute(
        """SELECT amount
        FROM season_daily
        WHERE user_id=?
        AND season=?
        AND day=?
        AND key=?""",
        (
            user_id,
            sid,
            today(),
            key
        )
    ).fetchone()

    used=(
        int(row["amount"])
        if row
        else 0
    )

    add=max(
        0,
        min(
            int(amount),
            int(cap)-used
        )
    )

    if add:
        con.execute(
            """INSERT INTO season_daily(
                user_id,season,day,key,amount
            ) VALUES(?,?,?,?,?)
            ON CONFLICT(user_id,season,day,key)
            DO UPDATE SET
                amount=amount+excluded.amount""",
            (
                user_id,
                sid,
                today(),
                key,
                add
            )
        )

    return add

def addxpcon(
    con,
    user_id,
    data,
    key,
    amount,
    cap
):
    touch(
        con,
        user_id,
        data["id"]
    )

    add=allowance(
        con,
        user_id,
        data["id"],
        key,
        amount,
        cap
    )

    if not add:
        return 0

    row=con.execute(
        """SELECT xp
        FROM season_users
        WHERE user_id=?
        AND season=?""",
        (
            user_id,
            data["id"]
        )
    ).fetchone()

    add=min(
        add,
        MAX_XP-int(
            row["xp"]
        )
    )

    if add>0:
        con.execute(
            """UPDATE season_users
            SET xp=xp+?
            WHERE user_id=?
            AND season=?""",
            (
                add,
                user_id,
                data["id"]
            )
        )

    return max(
        0,
        add
    )

def xp(
    user_id,
    key,
    amount,
    cap
):
    data=current()

    if data is None:
        return 0

    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        return addxpcon(
            con,
            user_id,
            data,
            key,
            amount,
            cap
        )

def commandxp(
    user_id,
    name
):
    cfg=COMMAND_XP.get(
        str(name or "")
    )

    if cfg is None:
        return 0

    return xp(
        user_id,
        f"command:{name}",
        cfg[0],
        cfg[1]
    )

def messagexp(user_id):
    data=current()

    if data is None:
        return 0

    now=time.time()

    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        row=con.execute(
            """SELECT last_at
            FROM season_messages
            WHERE user_id=?
            AND season=?""",
            (
                user_id,
                data["id"]
            )
        ).fetchone()

        if (
            row
            and now-float(
                row["last_at"]
            )<180
        ):
            return 0

        con.execute(
            """INSERT INTO season_messages(
                user_id,season,last_at
            ) VALUES(?,?,?)
            ON CONFLICT(user_id,season)
            DO UPDATE SET
                last_at=excluded.last_at""",
            (
                user_id,
                data["id"],
                now
            )
        )

        return addxpcon(
            con,
            user_id,
            data,
            "messages",
            1,
            10
        )

def state(user_id):
    data=current()

    if (
        data is None
        and datetime.now(ET)<HALLOW_START
    ):
        data=preview()

    if data is None:
        return None

    with connect() as con:
        touch(
            con,
            user_id,
            data["id"]
        )

        row=con.execute(
            """SELECT xp,paid,paid_guild_id
            FROM season_users
            WHERE user_id=?
            AND season=?""",
            (
                user_id,
                data["id"]
            )
        ).fetchone()

        claims={
            (
                found["track"],
                int(
                    found["tier"]
                )
            )
            for found in con.execute(
                """SELECT track,tier
                FROM season_claims
                WHERE user_id=?
                AND season=?""",
                (
                    user_id,
                    data["id"]
                )
            )
        }

    value=int(
        row["xp"]
    )

    return {
        "season":data,
        "xp":value,
        "tier":min(
            10,
            value//TIER_XP
        ),
        "paid":bool(
            row["paid"]
        ),
        "paid_guild_id":row["paid_guild_id"],
        "claims":claims
    }

def buy(guild_id,user_id):
    data=current()

    if (
        data is None
        and datetime.now(ET)<HALLOW_START
    ):
        data=preview()

    if data is None:
        return {
            "ok":False,
            "reason":"inactive"
        }

    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        touch(
            con,
            user_id,
            data["id"]
        )

        row=con.execute(
            """SELECT paid
            FROM season_users
            WHERE user_id=?
            AND season=?""",
            (
                user_id,
                data["id"]
            )
        ).fetchone()

        if row["paid"]:
            return {
                "ok":False,
                "reason":"owned"
            }

        con.execute(
            """INSERT OR IGNORE INTO wallets(guild_id,user_id)
            VALUES(?,?)""",
            (
                guild_id,
                user_id
            )
        )

        rings=int(
            con.execute(
                """SELECT rings
                FROM wallets
                WHERE guild_id=?
                AND user_id=?""",
                (
                    guild_id,
                    user_id
                )
            ).fetchone()["rings"]
        )

        if rings<PASS_COST:
            return {
                "ok":False,
                "reason":"rings",
                "need":
                    PASS_COST-rings
            }

        con.execute(
            """UPDATE wallets
            SET rings=rings-?
            WHERE guild_id=?
            AND user_id=?""",
            (
                PASS_COST,
                guild_id,
                user_id
            )
        )

        con.execute(
            """UPDATE season_users
            SET paid=1,
                paid_guild_id=?
            WHERE user_id=?
            AND season=?""",
            (
                guild_id,
                user_id,
                data["id"]
            )
        )

    return {
        "ok":True
    }

def additem(
    con,
    user_id,
    sid,
    key,
    amount
):
    con.execute(
        """INSERT INTO season_items(
            user_id,season,item,amount
        ) VALUES(?,?,?,?)
        ON CONFLICT(user_id,season,item)
        DO UPDATE SET
            amount=amount+excluded.amount""",
        (
            user_id,
            sid,
            key,
            amount
        )
    )

def addbottle(
    con,
    user_id,
    sid,
    key,
    amount=1
):
    con.execute(
        """INSERT INTO season_bottles(
            user_id,season,potion,amount
        ) VALUES(?,?,?,?)
        ON CONFLICT(user_id,season,potion)
        DO UPDATE SET
            amount=amount+excluded.amount""",
        (
            user_id,
            sid,
            key,
            amount
        )
    )

def tierbonus(
    con,
    user_id,
    data,
    track,
    tier
):
    if not data[
        "halloween"
    ]:
        return

    sid=data["id"]

    if (
        track=="free"
        and tier in (
            2,
            6
        )
    ):
        for key in INGREDIENTS:
            additem(
                con,
                user_id,
                sid,
                key,
                1
            )

    if (
        track=="paid"
        and tier in (
            1,
            9
        )
    ):
        for key in INGREDIENTS:
            additem(
                con,
                user_id,
                sid,
                key,
                2
            )

    potion={
        ("free",4):"jack",
        ("free",8):"spider",
        ("free",10):"witchlight",
        ("paid",3):"jack",
        ("paid",5):"marrow",
        ("paid",7):"spider",
        ("paid",10):"witchlight"
    }.get(
        (
            track,
            tier
        )
    )

    if potion:
        addbottle(
            con,
            user_id,
            sid,
            potion
        )

def claim(guild_id,user_id):
    data=current()

    if data is None:
        return {
            "ok":False,
            "reason":"inactive"
        }

    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        touch(
            con,
            user_id,
            data["id"]
        )

        user=con.execute(
            """SELECT xp,paid,paid_guild_id
            FROM season_users
            WHERE user_id=?
            AND season=?""",
            (
                user_id,
                data["id"]
            )
        ).fetchone()

        reached=min(
            10,
            int(
                user["xp"]
            )//TIER_XP
        )

        tracks=[
            (
                "free",
                FREE
            )
        ]

        if user["paid"]:
            tracks.append(
                (
                    "paid",
                    PAID
                )
            )

        roses=0
        rings=0
        wallets={}
        count=0

        for track,rewards in tracks:
            for tier in range(
                1,
                reached+1
            ):
                found=con.execute(
                    """SELECT 1
                    FROM season_claims
                    WHERE user_id=?
                    AND season=?
                    AND track=?
                    AND tier=?""",
                    (
                        user_id,
                        data["id"],
                        track,
                        tier
                    )
                ).fetchone()

                if found:
                    continue

                con.execute(
                    """INSERT INTO season_claims(
                        user_id,
                        season,
                        track,
                        tier,
                        claimed_at
                    ) VALUES(?,?,?,?,?)""",
                    (
                        user_id,
                        data["id"],
                        track,
                        tier,
                        time.time()
                    )
                )

                reward_roses=rewards[
                    tier
                ]

                reward_rings=(
                    1
                    if (
                        track=="paid"
                        and tier in (
                            6,
                            10
                        )
                    )
                    else 0
                )

                roses+=reward_roses
                rings+=reward_rings

                reward_guild=(
                    guild_id
                    if track=="free"
                    else user["paid_guild_id"]
                )

                if reward_guild is None:
                    raise RuntimeError(
                        "season paid wallet guild missing"
                    )

                wallet=wallets.setdefault(
                    int(reward_guild),
                    [0,0]
                )

                wallet[0]+=reward_roses
                wallet[1]+=reward_rings

                tierbonus(
                    con,
                    user_id,
                    data,
                    track,
                    tier
                )

                count+=1

        if count:
            for wallet_guild,(wallet_roses,wallet_rings) in wallets.items():
                con.execute(
                    """INSERT OR IGNORE INTO wallets(guild_id,user_id)
                    VALUES(?,?)""",
                    (
                        wallet_guild,
                        user_id
                    )
                )

                con.execute(
                    """UPDATE wallets
                    SET roses=roses+?,
                        rings=rings+?
                    WHERE guild_id=?
                    AND user_id=?""",
                    (
                        wallet_roses,
                        wallet_rings,
                        wallet_guild,
                        user_id
                    )
                )

    return {
        "ok":True,
        "count":count,
        "roses":roses,
        "rings":rings,
        "wallets":wallets
    }

def inventory(user_id):
    data=current()

    if data is None:
        return {
            "items":{
                key:0
                for key in INGREDIENTS
            },
            "bottles":{
                key:0
                for key in RECIPES
            }
        }

    with connect() as con:
        items={
            row["item"]:
                int(
                    row["amount"]
                )
            for row in con.execute(
                """SELECT item,amount
                FROM season_items
                WHERE user_id=?
                AND season=?""",
                (
                    user_id,
                    data["id"]
                )
            )
        }

        bottles={
            row["potion"]:
                int(
                    row["amount"]
                )
            for row in con.execute(
                """SELECT potion,amount
                FROM season_bottles
                WHERE user_id=?
                AND season=?""",
                (
                    user_id,
                    data["id"]
                )
            )
        }

    return {
        "items":{
            key:items.get(
                key,
                0
            )
            for key in INGREDIENTS
        },
        "bottles":{
            key:bottles.get(
                key,
                0
            )
            for key in RECIPES
        }
    }

def effect(
    user_id,
    key
):
    data=current()

    if data is None:
        return 0

    with connect() as con:
        row=con.execute(
            """SELECT amount
            FROM season_effects
            WHERE user_id=?
            AND season=?
            AND effect=?""",
            (
                user_id,
                data["id"],
                key
            )
        ).fetchone()

    return (
        int(
            row["amount"]
        )
        if row
        else 0
    )

def useeffect(
    user_id,
    key,
    amount
):
    data=current()

    if data is None:
        return 0

    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        row=con.execute(
            """SELECT amount
            FROM season_effects
            WHERE user_id=?
            AND season=?
            AND effect=?""",
            (
                user_id,
                data["id"],
                key
            )
        ).fetchone()

        have=(
            int(
                row["amount"]
            )
            if row
            else 0
        )

        used=min(
            have,
            amount
        )

        if used:
            con.execute(
                """UPDATE season_effects
                SET amount=amount-?
                WHERE user_id=?
                AND season=?
                AND effect=?""",
                (
                    used,
                    user_id,
                    data["id"],
                    key
                )
            )

    return used

def brew(
    user_id,
    key
):
    data=current()

    if (
        data is None
        or not data["halloween"]
        or key not in RECIPES
    ):
        return {
            "ok":False,
            "reason":"inactive"
        }

    cfg=RECIPES[
        key
    ]

    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        items={
            row["item"]:
                int(
                    row["amount"]
                )
            for row in con.execute(
                """SELECT item,amount
                FROM season_items
                WHERE user_id=?
                AND season=?""",
                (
                    user_id,
                    data["id"]
                )
            )
        }

        missing={
            item:
                amount-items.get(
                    item,
                    0
                )
            for item,amount
            in cfg["cost"].items()
            if items.get(
                item,
                0
            )<amount
        }

        if missing:
            return {
                "ok":False,
                "reason":"ingredients",
                "missing":missing
            }

        for item,amount in cfg[
            "cost"
        ].items():
            con.execute(
                """UPDATE season_items
                SET amount=amount-?
                WHERE user_id=?
                AND season=?
                AND item=?""",
                (
                    amount,
                    user_id,
                    data["id"],
                    item
                )
            )

        addbottle(
            con,
            user_id,
            data["id"],
            key
        )

    return {
        "ok":True
    }

def drink(
    user_id,
    key
):
    data=current()

    if (
        data is None
        or not data["halloween"]
        or key not in RECIPES
    ):
        return {
            "ok":False,
            "reason":"inactive"
        }

    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        bottle=con.execute(
            """SELECT amount
            FROM season_bottles
            WHERE user_id=?
            AND season=?
            AND potion=?""",
            (
                user_id,
                data["id"],
                key
            )
        ).fetchone()

        if (
            bottle is None
            or int(
                bottle["amount"]
            )<1
        ):
            return {
                "ok":False,
                "reason":"bottle"
            }

        active=con.execute(
            """SELECT amount
            FROM season_effects
            WHERE user_id=?
            AND season=?
            AND effect=?""",
            (
                user_id,
                data["id"],
                key
            )
        ).fetchone()

        if (
            key in (
                "jack",
                "spider"
            )
            and active
            and int(
                active["amount"]
            )>0
        ):
            return {
                "ok":False,
                "reason":"active"
            }

        if key=="marrow":
            gained=addxpcon(
                con,
                user_id,
                data,
                "marrow",
                10,
                20
            )

            if not gained:
                return {
                    "ok":False,
                    "reason":"cap"
                }

            amount=0

        else:
            amount={
                "jack":8,
                "spider":5,
                "witchlight":1
            }[
                key
            ]

        con.execute(
            """UPDATE season_bottles
            SET amount=amount-1
            WHERE user_id=?
            AND season=?
            AND potion=?""",
            (
                user_id,
                data["id"],
                key
            )
        )

        if amount:
            con.execute(
                """INSERT INTO season_effects(
                    user_id,season,effect,amount
                ) VALUES(?,?,?,?)
                ON CONFLICT(user_id,season,effect)
                DO UPDATE SET
                    amount=amount+excluded.amount""",
                (
                    user_id,
                    data["id"],
                    key,
                    amount
                )
            )

    return {
        "ok":True,
        "amount":amount
    }

def choose(rows):
    n=secrets.randbelow(
        sum(
            row[0]
            for row in rows
        )
    )

    for row in rows:
        if n<row[0]:
            return row[1:]

        n-=row[0]

    raise RuntimeError(
        "season odds died"
    )

def foragebonus(
    user_id,
    location
):
    data=current()

    if (
        data is None
        or not data["halloween"]
        or secrets.randbelow(100)>=20
    ):
        return None

    tables={
        "rose_patch":(
            (50,"pumpkin"),
            (25,"wax"),
            (15,"web"),
            (10,"bone")
        ),
        "overgrowth":(
            (45,"web"),
            (25,"pumpkin"),
            (20,"wax"),
            (10,"bone")
        ),
        "after_dark":(
            (40,"wax"),
            (30,"web"),
            (20,"bone"),
            (10,"pumpkin")
        )
    }

    key=choose(
        tables[
            location
        ]
    )[0]

    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        if not allowance(
            con,
            user_id,
            data["id"],
            "ingredient:forage",
            1,
            10
        ):
            return None

        additem(
            con,
            user_id,
            data["id"],
            key,
            1
        )

    return key

def adventure(
    guild_id,
    user_id,
    key
):
    data=current()

    if (
        data is None
        or not data["halloween"]
        or key not in PLACES
    ):
        return {
            "ok":False,
            "reason":"inactive"
        }

    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        if not allowance(
            con,
            user_id,
            data["id"],
            "adventure",
            1,
            1
        ):
            return {
                "ok":False,
                "reason":"done"
            }

        gained=addxpcon(
            con,
            user_id,
            data,
            "adventure-xp",
            8,
            8
        )

        name,emoji,table=PLACES[
            key
        ]

        kind,item,amount=choose(
            table
        )

        if kind=="nothing":
            light=con.execute(
                """SELECT amount
                FROM season_effects
                WHERE user_id=?
                AND season=?
                AND effect='witchlight'""",
                (
                    user_id,
                    data["id"]
                )
            ).fetchone()

            if (
                light
                and int(
                    light["amount"]
                )>0
            ):
                con.execute(
                    """UPDATE season_effects
                    SET amount=amount-1
                    WHERE user_id=?
                    AND season=?
                    AND effect='witchlight'""",
                    (
                        user_id,
                        data["id"]
                    )
                )

                safe=[
                    row
                    for row in table
                    if row[1]!="nothing"
                ]

                kind,item,amount=choose(
                    safe
                )

        if kind=="item":
            additem(
                con,
                user_id,
                data["id"],
                item,
                amount
            )

        elif kind=="roses":
            con.execute(
                """INSERT OR IGNORE INTO wallets(guild_id,user_id)
                VALUES(?,?)""",
                (
                    guild_id,
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
                    guild_id,
                    user_id
                )
            )

    return {
        "ok":True,
        "name":name,
        "emoji":emoji,
        "kind":kind,
        "item":item,
        "amount":amount,
        "xp":gained
    }

def install():
    global INSTALLED

    if INSTALLED:
        return

    foragecmd=importlib.import_module(
        "commands.forage"
    )

    oldforage=brewing.forage
    oldloot=foragecmd.lootline

    def forage(
        user_id,
        location
    ):
        result=oldforage(
            user_id,
            location
        )

        if not result.get(
            "ok"
        ):
            return result

        if effect(
            user_id,
            "spider"
        )>0:
            normal=(
                "petal",
                "herb",
                "dew"
            )[
                secrets.randbelow(3)
            ]

            brewing.add(
                user_id,
                normal,
                1
            )

            result[
                "loot"
            ][normal]=(
                result[
                    "loot"
                ].get(
                    normal,
                    0
                )
                +1
            )

            useeffect(
                user_id,
                "spider",
                1
            )

        special=foragebonus(
            user_id,
            location
        )

        if special:
            result[
                "loot"
            ][special]=(
                result[
                    "loot"
                ].get(
                    special,
                    0
                )
                +1
            )

        return result

    def lootline(loot):
        normal={
            key:value
            for key,value
            in loot.items()
            if key in brewing.INGREDIENTS
        }

        base=oldloot(
            normal
        )

        extra=[]

        for key,amount in loot.items():
            if key not in INGREDIENTS:
                continue

            cfg=INGREDIENTS[
                key
            ]

            extra.append(
                f"{cfg['emoji']} "
                f"**+{amount} "
                f"{cfg['name'] if amount==1 else cfg['plural']}**"
            )

        return "\n".join(
            part
            for part in (
                base,
                "\n".join(
                    extra
                )
            )
            if part
        )

    brewing.forage=forage
    foragecmd.lootline=lootline

    garden=importlib.import_module(
        "commands.garden"
    )

    oldharvest=garden.harvest
    oldembed=garden.harvest_embed

    def harvest(user_id, guild_id):
        result = oldharvest(user_id, guild_id)
        if not result.get('ok'):
            return result
        charges = effect(user_id, 'jack')
        if charges < 1:
            return result
        values = []
        for key, row in result['groups'].items():
            values.extend([garden.PLANTS[key]['xp']] * int(row['count']))
        used = min(charges, len(values))
        extra = sum((value * 30 // 100 for value in values[:used]))
        if extra:
            with garden.connect() as con:
                con.execute('UPDATE garden_v2_users\n                    SET xp=xp+?\n                    WHERE user_id=?', (extra, user_id))
            useeffect(user_id, 'jack', used)
            result['season_gxp'] = extra
        return result

    def harvestembed(result):
        out=oldembed(
            result
        )

        extra=result.get(
            "season_gxp",
            0
        )

        if extra:
            out.description+=(
                f"\n🎃 jack-o'-tonic "
                f"⊹ **+{extra:,} GXP**"
            )

        return out

    garden.harvest=harvest
    garden.harvest_embed=harvestembed

    brewcmd=importlib.import_module(
        "commands.brew"
    )

    seasonal=importlib.import_module(
        "commands.season"
    )

    oldmain=brewcmd.Main.__init__

    def main(
        self,
        user_id
    ):
        oldmain(
            self,
            user_id
        )

        data=current()

        if (
            data
            and data[
                "halloween"
            ]
        ):
            self.add_item(
                seasonal.BrewsButton(
                    user_id
                )
            )

    brewcmd.Main.__init__=main

    INSTALLED=True
