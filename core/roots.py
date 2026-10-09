import importlib
import secrets
import sqlite3
import time
from contextvars import ContextVar

from core import database
from core import game
from core import emoji as rosieemoji

COSTS=(5000,10000,20000,35000,50000)

BRANCHES={
    "bloom":{
        "emoji":rosieemoji.ROSE,
        "name":"bloom",
        "nodes":(
            "bloom roses +1%",
            "bloom roses +2%",
            "bloom roses +3%",
            "bloom roses +4%",
            "bloom roses +5%"
        )
    },
    "briar":{
        "emoji":"🌿",
        "name":"briar",
        "nodes":(
            "forage energy 6",
            "forage energy 6 • regen 4m",
            "forage energy 6 • regen 4m • garden 5% faster",
            "forage energy 7 • regen 4m • garden 5% faster",
            "forage energy 7 • regen 3m • garden 5% faster • 10% free forage"
        )
    },
    "dew":{
        "emoji":"💧",
        "name":"dew",
        "nodes":(
            "rose tonic +1 charge",
            "tonic +1 • knowledge +1 charge",
            "both charge potions +2 charges",
            "both +2 charges • 10% second bottle",
            "both +2 charges • 20% second bottle"
        )
    },
    "thorn":{
        "emoji":"🩸",
        "name":"thorn",
        "nodes":(
            "boss damage +2%",
            "boss damage +3%",
            "boss damage +5%",
            "boss damage +6% • campaign roses +5%",
            "boss damage +8% • campaign roses +10%"
        )
    }
}

MILESTONES=(
    ("pluck50",rosieemoji.ROSE + ' pluck 50 times'),
    ("pluck100",rosieemoji.ROSE + ' pluck 100 times'),
    ("pluck250",rosieemoji.ROSE + ' pluck 250 times'),
    ("pluck500",rosieemoji.ROSE + ' pluck 500 times'),

    ("garden5","🌱 reach garden level 5"),
    ("garden10","🌱 reach garden level 10"),
    ("garden20","🌱 reach garden level 20"),
    ("garden40","🌱 reach garden level 40"),

    ("forage10","🌿 forage 10 times"),
    ("forage25","🌿 forage 25 times"),
    ("forage50","🌿 forage 50 times"),
    ("forage75","🌿 forage 75 times"),

    ("brew5","🧪 brew 5 bottles"),
    ("brew10","🧪 brew 10 bottles"),
    ("brew25","🧪 brew 25 bottles"),

    ("pet10","🐾 raise a pet to level 10"),
    ("pet25","🐾 raise a pet to level 25"),
    ("pet50","🐾 raise a pet to level 50"),

    ("campaign5",rosieemoji.ROSE + ' clear 5 campaigns'),
    ("boss1","🩸 defeat a boss")
)

def connect():
    con=sqlite3.connect(
        database.FILE,
        timeout=10
    )
    con.row_factory=sqlite3.Row
    return con

def init():
    with connect() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS roots_users(
                user_id INTEGER PRIMARY KEY,
                bloom INTEGER NOT NULL DEFAULT 0,
                briar INTEGER NOT NULL DEFAULT 0,
                dew INTEGER NOT NULL DEFAULT 0,
                thorn INTEGER NOT NULL DEFAULT 0
            )"""
        )

        con.execute(
            """CREATE TABLE IF NOT EXISTS roots_milestones(
                user_id INTEGER NOT NULL,
                milestone TEXT NOT NULL,
                earned_at REAL NOT NULL,
                PRIMARY KEY(user_id,milestone)
            )"""
        )

def touch(con,user_id):
    con.execute(
        "INSERT OR IGNORE INTO roots_users(user_id) VALUES(?)",
        (user_id,)
    )

def tables(con):
    return {
        row[0]
        for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }

def scalar(con,sql,args=(),default=0):
    try:
        row=con.execute(
            sql,
            args
        ).fetchone()

        if not row:
            return default

        value=row[0]

        return (
            default
            if value is None
            else int(value)
        )

    except sqlite3.Error:
        return default

def metrics(user_id):
    with connect() as con:
        names=tables(con)

        plucks=(
            scalar(
                con,
                "SELECT total FROM pluck_users WHERE user_id=?",
                (user_id,)
            )
            if "pluck_users" in names
            else 0
        )

        forage=(
            scalar(
                con,
                "SELECT total FROM forage_users WHERE user_id=?",
                (user_id,)
            )
            if "forage_users" in names
            else 0
        )

        brewed=(
            scalar(
                con,
                "SELECT brewed FROM brew_users WHERE user_id=?",
                (user_id,)
            )
            if "brew_users" in names
            else 0
        )

        petlevel=(
            scalar(
                con,
                "SELECT MAX(level) FROM pets WHERE user_id=?",
                (user_id,)
            )
            if "pets" in names
            else 0
        )

        clears=(
            scalar(
                con,
                """SELECT COUNT(*)
                FROM campaign_runs
                WHERE user_id=?
                AND status='cleared'""",
                (user_id,)
            )
            if "campaign_runs" in names
            else 0
        )

        defeats=(
            scalar(
                con,
                "SELECT defeats FROM boss_users WHERE user_id=?",
                (user_id,)
            )
            if "boss_users" in names
            else 0
        )

    gardenlevel=0

    try:
        with sqlite3.connect(
            game.DB,
            timeout=10
        ) as con:
            xp=scalar(
                con,
                "SELECT xp FROM garden_v2_users WHERE user_id=?",
                (user_id,)
            )

        gardenlevel=1+xp//250 if xp else 0

    except sqlite3.Error:
        pass

    return {
        "pluck":plucks,
        "garden":gardenlevel,
        "forage":forage,
        "brew":brewed,
        "pet":petlevel,
        "campaign":clears,
        "boss":defeats
    }

def progress(user_id):
    data=metrics(
        user_id
    )

    return {
        "pluck50":data["pluck"]>=50,
        "pluck100":data["pluck"]>=100,
        "pluck250":data["pluck"]>=250,
        "pluck500":data["pluck"]>=500,

        "garden5":data["garden"]>=5,
        "garden10":data["garden"]>=10,
        "garden20":data["garden"]>=20,
        "garden40":data["garden"]>=40,

        "forage10":data["forage"]>=10,
        "forage25":data["forage"]>=25,
        "forage50":data["forage"]>=50,
        "forage75":data["forage"]>=75,

        "brew5":data["brew"]>=5,
        "brew10":data["brew"]>=10,
        "brew25":data["brew"]>=25,

        "pet10":data["pet"]>=10,
        "pet25":data["pet"]>=25,
        "pet50":data["pet"]>=50,

        "campaign5":data["campaign"]>=5,
        "boss1":data["boss"]>=1
    }

def sync(user_id):
    now=time.time()
    values=progress(
        user_id
    )

    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        touch(
            con,
            user_id
        )

        for key,done in values.items():
            if done:
                con.execute(
                    """INSERT OR IGNORE INTO roots_milestones(
                        user_id,milestone,earned_at
                    ) VALUES(?,?,?)""",
                    (
                        user_id,
                        key,
                        now
                    )
                )

        earned=scalar(
            con,
            """SELECT COUNT(*)
            FROM roots_milestones
            WHERE user_id=?""",
            (user_id,)
        )

        row=con.execute(
            "SELECT * FROM roots_users WHERE user_id=?",
            (user_id,)
        ).fetchone()

    levels={
        key:int(row[key])
        for key in BRANCHES
    }

    grown=sum(
        levels.values()
    )

    return {
        "earned":earned,
        "buds":max(
            0,
            earned-grown
        ),
        "grown":grown,
        "levels":levels,
        "progress":values
    }

def level(user_id,branch):
    if branch not in BRANCHES:
        return 0

    with connect() as con:
        touch(
            con,
            user_id
        )

        row=con.execute(
            f"SELECT {branch} FROM roots_users WHERE user_id=?",
            (user_id,)
        ).fetchone()

    return int(
        row[0]
    )

def nature(levels):
    high=max(
        levels.values(),
        default=0
    )

    if high<=0:
        return "ungrown"

    winners=[
        key
        for key,value in levels.items()
        if value==high
    ]

    if len(winners)!=1:
        return "mixed"

    return winners[0]

def state(user_id):
    data=sync(
        user_id
    )

    data["nature"]=nature(
        data["levels"]
    )

    return data

def grow(guild_id,user_id,branch):
    if branch not in BRANCHES:
        return {
            "ok":False,
            "reason":"branch"
        }

    sync(
        user_id
    )

    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        touch(
            con,
            user_id
        )

        row=con.execute(
            "SELECT * FROM roots_users WHERE user_id=?",
            (user_id,)
        ).fetchone()

        current=int(
            row[branch]
        )

        if current>=5:
            return {
                "ok":False,
                "reason":"max"
            }

        earned=scalar(
            con,
            """SELECT COUNT(*)
            FROM roots_milestones
            WHERE user_id=?""",
            (user_id,)
        )

        grown=sum(
            int(row[key])
            for key in BRANCHES
        )

        if earned-grown<1:
            return {
                "ok":False,
                "reason":"bud"
            }

        cost=COSTS[
            current
        ]

        con.execute(
            "INSERT OR IGNORE INTO wallets(guild_id,user_id) VALUES(?,?)",
            (guild_id,user_id)
        )

        cur=con.execute(
            """UPDATE wallets
            SET roses=roses-?
            WHERE guild_id=?
            AND user_id=?
            AND roses>=?""",
            (
                cost,
                guild_id,
                user_id,
                cost
            )
        )

        if cur.rowcount!=1:
            roses=scalar(
                con,
                "SELECT roses FROM wallets WHERE guild_id=? AND user_id=?",
                (guild_id,user_id)
            )

            return {
                "ok":False,
                "reason":"roses",
                "need":max(
                    0,
                    cost-roses
                )
            }

        con.execute(
            f"""UPDATE roots_users
            SET {branch}={branch}+1
            WHERE user_id=?""",
            (user_id,)
        )

    data=state(
        user_id
    )

    return {
        "ok":True,
        "branch":branch,
        "level":current+1,
        "cost":cost,
        "state":data
    }

def bloom_pct(user_id,kind):
    if kind not in {
        "pluck",
        "garden",
        "pet"
    }:
        return 0

    return level(
        user_id,
        "bloom"
    )

def briar_max(user_id):
    n=level(
        user_id,
        "briar"
    )

    return (
        5
        +(1 if n>=1 else 0)
        +(1 if n>=4 else 0)
    )

def briar_regen(user_id):
    n=level(
        user_id,
        "briar"
    )

    return (
        300
        -(60 if n>=2 else 0)
        -(60 if n>=5 else 0)
    )

def briar_growth(user_id):
    return (
        5
        if level(
            user_id,
            "briar"
        )>=3
        else 0
    )

def dew_charge(user_id,potion):
    n=level(
        user_id,
        "dew"
    )

    if potion=="rose_tonic":
        return (
            (1 if n>=1 else 0)
            +(1 if n>=3 else 0)
        )

    if potion=="knowledge":
        return (
            (1 if n>=2 else 0)
            +(1 if n>=3 else 0)
        )

    return 0

def dew_double(user_id):
    n=level(
        user_id,
        "dew"
    )

    if n>=5:
        return 20

    if n>=4:
        return 10

    return 0

def thorn_boss(user_id):
    n=level(
        user_id,
        "thorn"
    )

    return (
        0,2,3,5,6,8
    )[n]

def thorn_campaign(user_id):
    n=level(
        user_id,
        "thorn"
    )

    return (
        10
        if n>=5
        else 5
        if n>=4
        else 0
    )

def rose_bonus(user_id,kind,amount):
    amount=max(
        0,
        int(amount)
    )

    pct=bloom_pct(
        user_id,
        kind
    )

    return (
        amount*pct//100
        if pct
        else 0
    )

def patch_pluck():
    pluck=importlib.import_module(
        "commands.pluck"
    )

    if getattr(
        pluck,
        "_roots_patch",
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

        extra=rose_bonus(
            user_id,
            "pluck",
            result.get(
                "value",
                0
            )
        )

        if extra:
            database.walletadd(
                guild_id,
                user_id,
                roses=extra
            )

        result[
            "roots_bonus"
        ]=extra

        return result

    def embed(result):
        out=old_embed(
            result
        )

        extra=result.get(
            "roots_bonus",
            0
        )

        if extra:
            out.description=(
                out.description or ""
            )+(
                f'\n{rosieemoji.ROSE} roots ⊹ **+{extra:,} roses {rosieemoji.ROSE}**'
            )

        return out

    pluck.pluck=run
    pluck.embed=embed
    pluck._roots_patch=True

def patch_garden():
    garden=importlib.import_module(
        "commands.garden"
    )

    if getattr(
        garden,
        "_roots_patch",
        False
    ):
        return

    old_plant=garden.plant
    old_all=garden.plant_all
    old_harvest=garden.harvest
    old_embed=garden.harvest_embed

    def speed(user_id,result):
        pct=briar_growth(
            user_id
        )

        if (
            not pct
            or not result.get("ok")
        ):
            return result

        plots=(
            result.get("plots")
            or [result.get("plot")]
        )

        plots=[
            plot
            for plot in plots
            if plot is not None
        ]

        if not plots:
            return result

        now=time.time()

        with garden.connect() as con:
            for plot in plots:
                row=con.execute(
                    """SELECT ready_at
                    FROM garden_v2_plants
                    WHERE user_id=?
                    AND plot=?""",
                    (
                        user_id,
                        plot
                    )
                ).fetchone()

                if not row:
                    continue

                ready=float(
                    row["ready_at"]
                )

                new=now+max(
                    0,
                    ready-now
                )*(100-pct)/100

                con.execute(
                    """UPDATE garden_v2_plants
                    SET ready_at=?
                    WHERE user_id=?
                    AND plot=?""",
                    (
                        new,
                        user_id,
                        plot
                    )
                )

                result["ready"]=min(
                    float(
                        result.get(
                            "ready",
                            new
                        )
                    ),
                    new
                )

        result[
            "roots_growth"
        ]=pct

        return result

    def plant(guild_id,user_id,key):
        return speed(
            user_id,
            old_plant(
                guild_id,
                user_id,
                key
            )
        )

    def plant_all(guild_id,user_id,key):
        return speed(
            user_id,
            old_all(
                guild_id,
                user_id,
                key
            )
        )

    def harvest(user_id,guild_id):
        result=old_harvest(
            user_id,
            guild_id
        )

        if not result.get(
            "ok"
        ):
            return result

        extra=0

        for wallet_guild,amount in result.get(
            "wallet_profit",
            {}
        ).items():
            bonus=rose_bonus(
                user_id,
                "garden",
                amount
            )

            if bonus:
                database.walletadd(
                    int(wallet_guild),
                    user_id,
                    roses=bonus
                )
                extra+=bonus

        result[
            "roots_bonus"
        ]=extra

        return result

    def embed(result):
        out=old_embed(
            result
        )

        extra=result.get(
            "roots_bonus",
            0
        )

        if extra:
            out.description=(
                out.description or ""
            )+(
                f'\n{rosieemoji.ROSE} roots ⊹ **+{extra:,} roses {rosieemoji.ROSE}**'
            )

        return out

    garden.plant=plant
    garden.plant_all=plant_all
    garden.harvest=harvest
    garden.harvest_embed=embed
    garden._roots_patch=True

def patch_pet():
    pet=importlib.import_module(
        "commands.pet"
    )

    if getattr(
        pet,
        "_roots_patch",
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

        extra=rose_bonus(
            user_id,
            "pet",
            result.get(
                "reward",
                0
            )
        )

        if extra:
            database.walletadd(
                guild_id,
                user_id,
                roses=extra
            )

            try:
                species=result[
                    "pet"
                ][
                    "species"
                ]

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

            except Exception:
                pass

        result[
            "roots_bonus"
        ]=extra

        return result

    def note(result,kind):
        text=old_note(
            result,
            kind
        )

        extra=result.get(
            "roots_bonus",
            0
        )

        if (
            kind=="explore"
            and extra
        ):
            text+=(
                f'\n{rosieemoji.ROSE} roots ⊹ **+{extra:,} roses {rosieemoji.ROSE}**'
            )

        return text

    pet.do_explore=explore
    pet.action_note=note
    pet._roots_patch=True

def patch_forage():
    brewing=importlib.import_module("core.brewing")

    if getattr(
        brewing,
        "_roots_forage_patch",
        False
    ):
        return

    old_state=brewing.forage_state
    old_forage=brewing.forage

    def configured(fn,user_id,*args):
        old_max=brewing.MAX_ENERGY
        old_regen=brewing.ENERGY_REGEN

        brewing.MAX_ENERGY=briar_max(
            user_id
        )

        brewing.ENERGY_REGEN=briar_regen(
            user_id
        )

        try:
            return fn(
                user_id,
                *args
            )
        finally:
            brewing.MAX_ENERGY=old_max
            brewing.ENERGY_REGEN=old_regen

    def forage_state(user_id):
        return configured(
            old_state,
            user_id
        )

    def forage(user_id,place):
        result=configured(
            old_forage,
            user_id,
            place
        )

        if (
            result.get("ok")
            and level(
                user_id,
                "briar"
            )>=5
            and secrets.randbelow(100)<10
        ):
            cap=briar_max(
                user_id
            )

            with brewing.connect() as con:
                con.execute(
                    """UPDATE forage_users
                    SET energy=MIN(?,energy+1)
                    WHERE user_id=?""",
                    (
                        cap,
                        user_id
                    )
                )

            result[
                "energy"
            ]=min(
                cap,
                int(
                    result.get(
                        "energy",
                        0
                    )
                )+1
            )

            result[
                "roots_free"
            ]=True

        return result

    brewing.forage_state=forage_state
    brewing.forage=forage
    brewing._roots_forage_patch=True

def patch_brewing():
    brewing=importlib.import_module("core.brewing")

    if getattr(
        brewing,
        "_roots_brew_patch",
        False
    ):
        return

    old_make=brewing.make
    old_activate=brewing.activate

    def make(user_id,potion):
        result=old_make(
            user_id,
            potion
        )

        if not result.get(
            "ok"
        ):
            return result

        chance=dew_double(
            user_id
        )

        if (
            chance
            and secrets.randbelow(100)<chance
        ):
            with brewing.connect() as con:
                con.execute(
                    """INSERT INTO brew_bottles(
                        user_id,potion,amount
                    ) VALUES(?,?,1)
                    ON CONFLICT(user_id,potion)
                    DO UPDATE SET
                        amount=amount+1""",
                    (
                        user_id,
                        potion
                    )
                )

            result[
                "roots_double"
            ]=True

        return result

    def activate(user_id,potion):
        result=old_activate(
            user_id,
            potion
        )

        if not result.get(
            "ok"
        ):
            return result

        extra=dew_charge(
            user_id,
            potion
        )

        if not extra:
            return result

        column=(
            "rose_charges"
            if potion=="rose_tonic"
            else "gxp_charges"
            if potion=="knowledge"
            else None
        )

        if column is None:
            return result

        with brewing.connect() as con:
            con.execute(
                f"""UPDATE brew_users
                SET {column}={column}+?
                WHERE user_id=?""",
                (
                    extra,
                    user_id
                )
            )

            charges=con.execute(
                f"""SELECT {column}
                FROM brew_users
                WHERE user_id=?""",
                (
                    user_id,
                )
            ).fetchone()[0]

        result[
            "charges"
        ]=int(
            charges
        )

        result[
            "roots_charges"
        ]=extra

        return result

    brewing.make=make
    brewing.activate=activate
    brewing._roots_brew_patch=True

def patch_campaign():
    campaign=importlib.import_module(
        "commands.campaign"
    )

    if getattr(
        campaign,
        "_roots_patch",
        False
    ):
        return

    old_step=campaign.step

    def step(run_id,user_id,node,tester=False):
        result=old_step(
            run_id,
            user_id,
            node,
            tester
        )

        if (
            not result.get("ok")
            or not result.get("done")
        ):
            return result

        pct=thorn_campaign(
            user_id
        )

        if not pct:
            return result

        data=result.get(
            "run",
            {}
        )

        base=max(
            0,
            int(
                data.get(
                    "pot",
                    0
                )
            )
        )

        extra=base*pct//100

        if extra:
            guild_id=data.get(
                "guild_id"
            )

            if guild_id is None:
                raise RuntimeError(
                    "campaign wallet guild missing"
                )

            database.walletadd(
                guild_id,
                user_id,
                roses=extra
            )

            data[
                "pot"
            ]=base+extra

            result[
                "roots_bonus"
            ]=extra

        return result

    campaign.step=step
    campaign._roots_patch=True

def patch_boss():
    boss=importlib.import_module(
        "commands.boss"
    )

    if getattr(
        boss,
        "_roots_patch",
        False
    ):
        return

    old_damage=boss.damage
    old_act=boss.act

    boost=ContextVar(
        "rosie_roots_boss_pct",
        default=0
    )

    extra=ContextVar(
        "rosie_roots_boss_bonus",
        default=0
    )

    def damage(action,correct):
        dealt,status=old_damage(
            action,
            correct
        )

        pct=boost.get()

        amount=(
            dealt*pct//100
            if pct
            else 0
        )

        extra.set(
            amount
        )

        return (
            dealt+amount,
            status
        )

    def act(
        guild_id,
        message_id,
        user_id,
        action
    ):
        pct=thorn_boss(
            user_id
        )

        boost_token=boost.set(
            pct
        )

        bonus_token=extra.set(
            0
        )

        try:
            result=old_act(
                guild_id,
                message_id,
                user_id,
                action
            )

            if result.get(
                "ok"
            ):
                result[
                    "roots_bonus"
                ]=extra.get()

            return result

        finally:
            boost.reset(
                boost_token
            )

            extra.reset(
                bonus_token
            )

    boss.damage=damage
    boss.act=act
    boss._roots_patch=True

def install():
    init()

    patch_pluck()
    patch_garden()
    patch_pet()
    patch_forage()
    patch_brewing()
    patch_campaign()
    patch_boss()


# campaign root metric fix
oldmetrics=metrics

def metrics(user_id):
    data=dict(oldmetrics(user_id))

    import sqlite3
    from core import database

    with sqlite3.connect(database.FILE,timeout=10) as con:
        data["campaign"]=con.execute(
            """SELECT COUNT(*)
            FROM campaign_runs
            WHERE user_id=? AND status='cleared'""",
            (user_id,)
        ).fetchone()[0]

    return data
