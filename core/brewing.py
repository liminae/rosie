import importlib
import secrets
import sqlite3
import time

from core import database
from core import emoji as rosieemoji

MAX_ENERGY=5
ENERGY_REGEN=300

INGREDIENTS={
    "petal":{
        "name":"petal",
        "plural":"petals",
        "emoji":rosieemoji.ROSE
    },
    "herb":{
        "name":"herb",
        "plural":"herbs",
        "emoji":"🌿"
    },
    "dew":{
        "name":"dew",
        "plural":"dew",
        "emoji":"💧"
    }
}

RECIPES={
    "rose_tonic":{
        "name":"rose tonic",
        "emoji":rosieemoji.ROSE,
        "cost":{
            "petal":15,
            "herb":6
        },
        "text":"+15% on your next 10 pluck, garden profit + pet explore rewards",
        "charges":10
    },
    "knowledge":{
        "name":"knowledge",
        "emoji":"🌱",
        "cost":{
            "petal":12,
            "herb":9
        },
        "text":"+25% GXP on your next 10 harvested plants",
        "charges":10
    },
    "overgrowth":{
        "name":"overgrowth",
        "emoji":"🌿",
        "cost":{
            "herb":9,
            "dew":3
        },
        "text":"remove 25% of remaining grow time from every planted crop",
        "charges":0
    },
    "second_wind":{
        "name":"second wind",
        "emoji":"🐾",
        "cost":{
            "petal":6,
            "dew":3
        },
        "text":"restore 30 pet energy",
        "charges":0
    }
}

FORAGE={
    "rose_patch":{
        "name":"rose patch",
        "emoji":rosieemoji.ROSE,
        "objects":(
            "thorny bush",
            "fallen petals",
            "old trellis",
            "cracked pot",
            "something red"
        ),
        "loot":(
            (5000,{"petal":1}),
            (2500,{"petal":2}),
            (1500,{"herb":1}),
            (800,{"petal":1,"herb":1}),
            (200,{"dew":1})
        )
    },
    "overgrowth":{
        "name":"overgrowth",
        "emoji":"🌲",
        "objects":(
            "fallen log",
            "mushrooms",
            "tangled brush",
            "tree roots",
            "old stump"
        ),
        "loot":(
            (2000,{"petal":1}),
            (5000,{"herb":1}),
            (1500,{"herb":2}),
            (1000,{"petal":1,"herb":1}),
            (500,{"dew":1})
        )
    },
    "after_dark":{
        "name":"after dark",
        "emoji":"🌙",
        "objects":(
            "hollow tree",
            "moonlit puddle",
            "moving grass",
            "cold stone",
            "something shiny"
        ),
        "loot":(
            (2000,{"petal":1}),
            (4000,{"herb":1}),
            (2500,{"dew":1}),
            (1000,{"petal":1,"herb":1}),
            (500,{"dew":2})
        )
    }
}

INSTALLED=False

def connect():
    con=sqlite3.connect(
        database.FILE,
        timeout=10
    )
    con.row_factory=sqlite3.Row
    return con

def init():
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS brew_users(
            user_id INTEGER PRIMARY KEY,
            petal INTEGER NOT NULL DEFAULT 0,
            herb INTEGER NOT NULL DEFAULT 0,
            dew INTEGER NOT NULL DEFAULT 0,
            rose_charges INTEGER NOT NULL DEFAULT 0,
            gxp_charges INTEGER NOT NULL DEFAULT 0,
            brewed INTEGER NOT NULL DEFAULT 0,
            rose_finished_at REAL,
            gxp_finished_at REAL
        )""")

        cols={
            row[1]
            for row in con.execute(
                "PRAGMA table_info(brew_users)"
            )
        }

        for name in (
            "rose_finished_at",
            "gxp_finished_at"
        ):
            if name not in cols:
                con.execute(
                    f"ALTER TABLE brew_users "
                    f"ADD COLUMN {name} REAL"
                )

        con.execute("""CREATE TABLE IF NOT EXISTS brew_bottles(
            user_id INTEGER NOT NULL,
            potion TEXT NOT NULL,
            amount INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id,potion)
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS forage_users(
            user_id INTEGER PRIMARY KEY,
            energy INTEGER NOT NULL DEFAULT 5,
            energy_at REAL NOT NULL,
            total INTEGER NOT NULL DEFAULT 0
        )""")

def touch(con,user_id,now=None):
    now=now or time.time()

    con.execute(
        """INSERT OR IGNORE INTO brew_users(user_id)
        VALUES(?)""",
        (user_id,)
    )

    con.execute(
        """INSERT OR IGNORE INTO forage_users(
            user_id,energy,energy_at
        ) VALUES(?,?,?)""",
        (
            user_id,
            MAX_ENERGY,
            now
        )
    )

def inventory(user_id):
    with connect() as con:
        touch(
            con,
            user_id
        )

        row=con.execute(
            """SELECT *
            FROM brew_users
            WHERE user_id=?""",
            (user_id,)
        ).fetchone()

        bottles={
            found["potion"]:
                int(found["amount"])
            for found in con.execute(
                """SELECT potion,amount
                FROM brew_bottles
                WHERE user_id=?""",
                (user_id,)
            )
        }

    return {
        "petal":int(row["petal"]),
        "herb":int(row["herb"]),
        "dew":int(row["dew"]),
        "rose_charges":int(
            row["rose_charges"]
        ),
        "gxp_charges":int(
            row["gxp_charges"]
        ),
        "brewed":int(
            row["brewed"]
        ),
        "bottles":{
            key:bottles.get(
                key,
                0
            )
            for key in RECIPES
        }
    }

def add(user_id,key,amount=1):
    if (
        key not in INGREDIENTS
        or amount<1
    ):
        return

    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        touch(
            con,
            user_id
        )

        con.execute(
            f"""UPDATE brew_users
            SET {key}={key}+?
            WHERE user_id=?""",
            (
                int(amount),
                user_id
            )
        )

def missing(user_id,key):
    cfg=RECIPES[
        key
    ]

    data=inventory(
        user_id
    )

    return {
        name:max(
            0,
            amount-data[name]
        )
        for name,amount
        in cfg["cost"].items()
        if data[name]<amount
    }

def make(user_id,key):
    if key not in RECIPES:
        return {
            "ok":False,
            "reason":"invalid"
        }

    cfg=RECIPES[
        key
    ]

    need={
        name:int(
            cfg["cost"].get(
                name,
                0
            )
        )
        for name in INGREDIENTS
    }

    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        touch(
            con,
            user_id
        )

        row=con.execute(
            """SELECT petal,herb,dew
            FROM brew_users
            WHERE user_id=?""",
            (user_id,)
        ).fetchone()

        miss={
            name:max(
                0,
                need[name]-int(row[name])
            )
            for name in INGREDIENTS
            if int(row[name])<need[name]
        }

        if miss:
            return {
                "ok":False,
                "reason":"ingredients",
                "missing":miss
            }

        con.execute(
            """UPDATE brew_users
            SET petal=petal-?,
                herb=herb-?,
                dew=dew-?,
                brewed=brewed+1
            WHERE user_id=?""",
            (
                need["petal"],
                need["herb"],
                need["dew"],
                user_id
            )
        )

        con.execute(
            """INSERT INTO brew_bottles(
                user_id,potion,amount
            ) VALUES(?,?,1)
            ON CONFLICT(user_id,potion)
            DO UPDATE SET
                amount=amount+1""",
            (
                user_id,
                key
            )
        )

    return {
        "ok":True,
        "key":key
    }

def bottle(user_id,key):
    with connect() as con:
        row=con.execute(
            """SELECT amount
            FROM brew_bottles
            WHERE user_id=?
            AND potion=?""",
            (
                user_id,
                key
            )
        ).fetchone()

    return (
        int(row["amount"])
        if row
        else 0
    )

def take(user_id,key):
    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        row=con.execute(
            """SELECT amount
            FROM brew_bottles
            WHERE user_id=?
            AND potion=?""",
            (
                user_id,
                key
            )
        ).fetchone()

        if (
            row is None
            or int(row["amount"])<1
        ):
            return False

        con.execute(
            """UPDATE brew_bottles
            SET amount=amount-1
            WHERE user_id=?
            AND potion=?""",
            (
                user_id,
                key
            )
        )

    return True

def activate(user_id,key):
    cols={
        "rose_tonic":(
            "rose_charges",
            "rose_finished_at"
        ),
        "knowledge":(
            "gxp_charges",
            "gxp_finished_at"
        )
    }

    if key not in cols:
        return {
            "ok":False,
            "reason":"invalid"
        }

    col,finished=cols[key]

    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        touch(
            con,
            user_id
        )

        row=con.execute(
            f"""SELECT {col}
            FROM brew_users
            WHERE user_id=?""",
            (user_id,)
        ).fetchone()

        charges=int(
            row[col]
        )

        if charges>0:
            return {
                "ok":False,
                "reason":"active",
                "charges":charges
            }

        found=con.execute(
            """SELECT amount
            FROM brew_bottles
            WHERE user_id=?
            AND potion=?""",
            (
                user_id,
                key
            )
        ).fetchone()

        if (
            found is None
            or int(found["amount"])<1
        ):
            return {
                "ok":False,
                "reason":"none"
            }

        con.execute(
            """UPDATE brew_bottles
            SET amount=amount-1
            WHERE user_id=?
            AND potion=?""",
            (
                user_id,
                key
            )
        )

        con.execute(
            f"""UPDATE brew_users
            SET {col}=10,
                {finished}=NULL
            WHERE user_id=?""",
            (user_id,)
        )

    return {
        "ok":True,
        "charges":10
    }

def rose_bonus(user_id,amount):
    amount=max(
        0,
        int(amount)
    )

    if amount<=0:
        return 0

    extra=min(
        100,
        amount*15//100
    )

    if extra<=0:
        return 0

    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        touch(
            con,
            user_id
        )

        row=con.execute(
            """SELECT rose_charges
            FROM brew_users
            WHERE user_id=?""",
            (user_id,)
        ).fetchone()

        charges=int(
            row["rose_charges"]
        )

        if charges<=0:
            return 0

        stamp=(
            time.time()
            if charges==1
            else None
        )

        con.execute(
            """UPDATE brew_users
            SET rose_charges=rose_charges-1,
                rose_finished_at=?
            WHERE user_id=?""",
            (
                stamp,
                user_id
            )
        )

    return extra

def gxp_bonus(user_id,values):
    values=[
        max(
            0,
            int(value)
        )
        for value in values
        if int(value)>0
    ]

    if not values:
        return 0,0

    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        touch(
            con,
            user_id
        )

        row=con.execute(
            """SELECT gxp_charges
            FROM brew_users
            WHERE user_id=?""",
            (user_id,)
        ).fetchone()

        charges=int(
            row["gxp_charges"]
        )

        used=min(
            charges,
            len(values)
        )

        if used<=0:
            return 0,0

        stamp=(
            time.time()
            if charges-used==0
            else None
        )

        con.execute(
            """UPDATE brew_users
            SET gxp_charges=
                    gxp_charges-?,
                gxp_finished_at=?
            WHERE user_id=?""",
            (
                used,
                stamp,
                user_id
            )
        )

    extra=sum(
        value*25//100
        for value in values[:used]
    )

    return extra,used

def _refresh(con,user_id,now):
    touch(
        con,
        user_id,
        now
    )

    row=con.execute(
        """SELECT *
        FROM forage_users
        WHERE user_id=?""",
        (user_id,)
    ).fetchone()

    energy=int(
        row["energy"]
    )

    at=float(
        row["energy_at"]
    )

    if energy<MAX_ENERGY:
        gain=max(
            0,
            int(
                (now-at)
                //ENERGY_REGEN
            )
        )

        if gain:
            energy=min(
                MAX_ENERGY,
                energy+gain
            )

            at=(
                now
                if energy>=MAX_ENERGY
                else at+gain*ENERGY_REGEN
            )

            con.execute(
                """UPDATE forage_users
                SET energy=?,
                    energy_at=?
                WHERE user_id=?""",
                (
                    energy,
                    at,
                    user_id
                )
            )

    return {
        "energy":energy,
        "energy_at":at,
        "total":int(
            row["total"]
        )
    }

def forage_state(user_id):
    now=time.time()

    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        data=_refresh(
            con,
            user_id,
            now
        )

    data["next"]=(
        None
        if data["energy"]>=MAX_ENERGY
        else data["energy_at"]
            +ENERGY_REGEN
    )

    data["max_energy"]=MAX_ENERGY
    data["regen"]=ENERGY_REGEN

    return data

def roll(location):
    n=secrets.randbelow(
        10000
    )

    for chance,loot in FORAGE[
        location
    ]["loot"]:
        if n<chance:
            return dict(
                loot
            )

        n-=chance

    raise RuntimeError(
        "forage odds died"
    )

def forage(user_id,location):
    if location not in FORAGE:
        return {
            "ok":False,
            "reason":"location"
        }

    now=time.time()

    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        data=_refresh(
            con,
            user_id,
            now
        )

        if data["energy"]<1:
            return {
                "ok":False,
                "reason":"energy",
                "next":
                    data["energy_at"]
                    +ENERGY_REGEN
            }

        energy=(
            data["energy"]-1
        )

        at=(
            now
            if data["energy"]
                >=MAX_ENERGY
            else data["energy_at"]
        )

        loot=roll(
            location
        )

        con.execute(
            """UPDATE forage_users
            SET energy=?,
                energy_at=?,
                total=total+1
            WHERE user_id=?""",
            (
                energy,
                at,
                user_id
            )
        )

        for key,amount in loot.items():
            con.execute(
                f"""UPDATE brew_users
                SET {key}={key}+?
                WHERE user_id=?""",
                (
                    int(amount),
                    user_id
                )
            )

    return {
        "ok":True,
        "location":location,
        "loot":loot,
        "energy":energy,
        "max_energy":MAX_ENERGY,
        "regen":ENERGY_REGEN,
        "next":(
            None
            if energy>=MAX_ENERGY
            else at+ENERGY_REGEN
        )
    }

def patch_pluck():
    pluck=importlib.import_module(
        "commands.pluck"
    )

    if getattr(
        pluck,
        "_brew_patch",
        False
    ):
        return

    old_run=pluck.pluck
    old_embed=pluck.embed

    def run(user_id,guild_id):
        result=old_run(
            user_id,
            guild_id
        )

        if not result.get(
            "ok"
        ):
            return result

        found=(
            secrets.randbelow(
                10000
            )<1000
        )

        if found:
            add(
                user_id,
                "petal",
                1
            )

            result[
                "brew_petal"
            ]=1

        extra=rose_bonus(
            user_id,
            result["value"]
        )

        if extra:
            database.walletadd(
                guild_id,
                user_id,
                roses=extra
            )

        result[
            "brew_rose_bonus"
        ]=extra

        return result

    def embed(result):
        out=old_embed(
            result
        )

        lines=[]

        if result.get(
            "brew_petal"
        ):
            lines.append(
                rosieemoji.ROSE + ' ⊹ **1 petal**'
            )

        if result.get(
            "brew_rose_bonus"
        ):
            lines.append(
                f"🧪 ⊹ **{result['brew_rose_bonus']:,} roses {rosieemoji.ROSE}**"
            )

        if lines:
            out.description=(
                out.description or ""
            )+"\n"+"\n".join(
                lines
            )

        return out

    pluck.pluck=run
    pluck.embed=embed
    pluck._brew_patch=True

def patch_garden():
    garden=importlib.import_module(
        "commands.garden"
    )

    if getattr(
        garden,
        "_brew_patch",
        False
    ):
        return

    old_harvest=garden.harvest
    old_embed=garden.harvest_embed

    def harvest(user_id,guild_id):
        result=old_harvest(
            user_id,
            guild_id
        )

        if not result.get(
            "ok"
        ):
            return result

        count=sum(
            int(data["count"])
            for data
            in result["groups"].values()
        )

        herbs=min(
            2,
            sum(
                secrets.randbelow(
                    10000
                )<1500
                for _ in range(
                    count
                )
            )
        )

        if herbs:
            add(
                user_id,
                "herb",
                herbs
            )

        rose=0

        for wallet_guild,amount in result.get(
            "wallet_profit",
            {}
        ).items():
            bonus=rose_bonus(
                user_id,
                amount
            )

            if bonus:
                database.walletadd(
                    int(wallet_guild),
                    user_id,
                    roses=bonus
                )
                rose+=bonus

        xp_values=[]

        for key,data in result[
            "groups"
        ].items():
            value=int(
                garden.PLANTS[
                    key
                ]["xp"]
            )

            xp_values.extend(
                [value]
                *int(
                    data["count"]
                )
            )

        gxp,used=gxp_bonus(
            user_id,
            xp_values
        )

        if gxp:
            with garden.connect() as con:
                con.execute(
                    "BEGIN IMMEDIATE"
                )

                row=con.execute(
                    """SELECT xp,plots
                    FROM garden_v2_users
                    WHERE user_id=?""",
                    (user_id,)
                ).fetchone()

                if row is not None:
                    newxp=(
                        int(row["xp"])
                        +gxp
                    )

                    con.execute(
                        """UPDATE garden_v2_users
                        SET xp=?
                        WHERE user_id=?""",
                        (
                            newxp,
                            user_id
                        )
                    )

                    if hasattr(
                        garden,
                        "legacy_user"
                    ):
                        garden.legacy_user(
                            con,
                            user_id,
                            newxp,
                            int(
                                row["plots"]
                            )
                        )

        result[
            "brew_herb"
        ]=herbs

        result[
            "brew_rose_bonus"
        ]=rose

        result[
            "brew_gxp_bonus"
        ]=gxp

        result[
            "brew_gxp_used"
        ]=used

        return result

    def embed(result):
        out=old_embed(
            result
        )

        lines=[]

        herbs=result.get(
            "brew_herb",
            0
        )

        if herbs:
            lines.append(
                f"🌿 ⊹ "
                f"**{herbs} "
                f"{'herb' if herbs==1 else 'herbs'}**"
            )

        if result.get(
            "brew_rose_bonus"
        ):
            lines.append(
                f"🧪 ⊹ **{result['brew_rose_bonus']:,} roses {rosieemoji.ROSE}**"
            )

        if result.get(
            "brew_gxp_bonus"
        ):
            lines.append(
                "🌱 ⊹ "
                f"**{result['brew_gxp_bonus']:,} GXP**"
            )

        if lines:
            out.description=(
                out.description or ""
            )+"\n"+"\n".join(
                lines
            )

        return out

    garden.harvest=harvest
    garden.harvest_embed=embed
    garden._brew_patch=True

def patch_pet():
    pet=importlib.import_module(
        "commands.pet"
    )

    if getattr(
        pet,
        "_brew_patch",
        False
    ):
        return

    old_explore=pet.do_explore
    old_note=pet.action_note

    def explore(user_id,guild_id):
        result=old_explore(
            user_id,
            guild_id
        )

        if not result.get(
            "ok"
        ):
            return result

        found=(
            secrets.randbelow(
                10000
            )<2500
        )

        if found:
            add(
                user_id,
                "dew",
                1
            )

            result[
                "brew_dew"
            ]=1

        extra=rose_bonus(
            user_id,
            result["reward"]
        )

        if extra:
            database.walletadd(
                guild_id,
                user_id,
                roses=extra
            )

            species=result[
                "pet"
            ]["species"]

            with pet.connect() as con:
                con.execute(
                    """UPDATE pets
                    SET earned=earned+?
                    WHERE user_id=?
                    AND species=?""",
                    (
                        extra,
                        user_id,
                        species
                    )
                )

                con.execute(
                    """UPDATE pet_users
                    SET earned=earned+?
                    WHERE user_id=?""",
                    (
                        extra,
                        user_id
                    )
                )

        result[
            "brew_rose_bonus"
        ]=extra

        return result

    def note(result,kind):
        text=old_note(
            result,
            kind
        )

        if kind!="explore":
            return text

        if result.get(
            "brew_dew"
        ):
            text+=(
                "\n💧 ⊹ "
                "**1 dew**"
            )

        if result.get(
            "brew_rose_bonus"
        ):
            text+=(
                f"\n🧪 ⊹ **{result['brew_rose_bonus']:,} roses {rosieemoji.ROSE}**"
            )

        return text

    pet.do_explore=explore
    pet.action_note=note
    pet._brew_patch=True

def install():
    global INSTALLED

    if INSTALLED:
        return

    init()
    patch_pluck()
    patch_garden()
    patch_pet()

    INSTALLED=True
