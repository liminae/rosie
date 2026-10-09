import importlib
import secrets
import sqlite3
import time
from contextvars import ContextVar

import discord
from core import database
from core import petcatalog
from core import emoji as rosieemoji

DURATION=10800
BUFFS=petcatalog.BUFFS
ALIASES=petcatalog.ALIASES

def connect():
    con=sqlite3.connect(
        database.FILE,
        timeout=10
    )
    con.row_factory=sqlite3.Row
    return con

def init():
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS pet_buffs(
            user_id INTEGER PRIMARY KEY,
            species TEXT NOT NULL,
            expires_at REAL NOT NULL
        )""")

def activate(user_id,species):
    info=BUFFS.get(species)

    if info is None:
        return None

    expires=time.time()+DURATION

    with connect() as con:
        con.execute("""INSERT INTO pet_buffs(
            user_id,species,expires_at
        ) VALUES(?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET
        species=excluded.species,
        expires_at=excluded.expires_at
        """,(user_id,species,expires))

    return {
        "species":species,
        "expires_at":expires,
        **info
    }

def get(user_id):
    now=time.time()

    with connect() as con:
        row=con.execute(
            "SELECT species,expires_at "
            "FROM pet_buffs WHERE user_id=?",
            (user_id,)
        ).fetchone()

        if row is None:
            return None

        if row["expires_at"]<=now:
            return None

    info=BUFFS.get(
        row["species"]
    )

    if info is None:
        return None

    return {
        "species":row["species"],
        "expires_at":row["expires_at"],
        **info
    }

def pct(user_id,key):
    buff=get(
        user_id
    )

    if not buff:
        return 0

    return int(
        buff.get(
            "effects",
            {}
        ).get(
            key,
            0
        )
    )

def bonus(user_id,key,amount):
    amount=max(
        0,
        int(
            amount
        )
    )

    return (
        amount
        *pct(
            user_id,
            key
        )
        //100
    )


def xppct(user_id):
    buff=get(
        user_id
    )

    return (
        int(
            buff.get(
                "xp_pct",
                0
            )
        )
        if buff
        else 0
    )


def findbonus(user_id):
    buff=get(
        user_id
    )

    return (
        int(
            buff.get(
                "find_bonus",
                0
            )
        )
        if buff
        else 0
    )

def species(option):
    value=str(
        getattr(option,"value","") or ""
    ).strip().lower()

    if value in BUFFS:
        return value

    value=value.replace("-","_").replace(" ","_")

    if value in BUFFS:
        return value

    label=str(
        getattr(option,"label","") or ""
    ).strip().lower()

    for name,key in ALIASES.items():
        if name in label:
            return key

    return None

def preview(key):
    buff=BUFFS[
        key
    ]

    return (
        f"{buff['label']} ⊹ "
        f"{buff['text']} ⊹ "
        "3h after play"
    )

def options(view):
    for item in getattr(view,"children",()):
        if not isinstance(
            item,
            discord.ui.Select
        ):
            continue

        for option in item.options:
            key=species(option)

            if key is None:
                continue

            perk=preview(key)
            old=(
                option.description
                or ""
            ).strip()

            if perk in old:
                continue

            text=(
                f"{old} ⊹ {perk}"
                if old
                else perk
            )

            if len(text)>100:
                keep=max(
                    0,
                    97-len(perk)
                )

                if keep:
                    old=old[:keep].rstrip(
                        " ⊹•-"
                    )

                    text=(
                        f"{old} ⊹ {perk}"
                        if old
                        else perk
                    )
                else:
                    text=perk

            option.description=text[:100]

def patch_views(pet):
    for cls in vars(pet).values():
        if (
            not isinstance(cls,type)
            or not issubclass(
                cls,
                discord.ui.View
            )
            or cls is discord.ui.View
            or cls.__module__!=pet.__name__
        ):
            continue

        if getattr(
            cls,
            "_petbuff_info",
            False
        ):
            continue

        old=cls.__init__

        def make(fn):
            def init(self,*args,**kwargs):
                fn(
                    self,
                    *args,
                    **kwargs
                )
                options(self)
            return init

        cls.__init__=make(old)
        cls._petbuff_info=True

def patch_pet():
    pet=importlib.import_module(
        "commands.pet"
    )

    if getattr(
        pet,
        "_petbuff_patch",
        False
    ):
        return

    patch_views(
        pet
    )

    old_feed=pet.do_feed
    old_play=pet.do_play
    old_explore=pet.do_explore
    old_note=pet.action_note
    old_panel=pet.panel

    def addxp(
        result,
        base
    ):
        if not result.get(
            "ok"
        ):
            return

        user_id=int(
            result[
                "pet"
            ][
                "user_id"
            ]
        )

        amount=(
            int(
                base
            )
            *xppct(
                user_id
            )
            //100
        )

        if amount<1:
            return

        species=result[
            "pet"
        ][
            "species"
        ]

        with pet.connect() as con:
            row=con.execute(
                """SELECT level,xp
                FROM pets
                WHERE user_id=?
                AND species=?""",
                (
                    user_id,
                    species
                )
            ).fetchone()

            if row is None:
                return

            level,xp,gained=pet.levelup(
                int(
                    row[
                        "level"
                    ]
                ),
                int(
                    row[
                        "xp"
                    ]
                ),
                amount
            )

            con.execute(
                """UPDATE pets
                SET level=?,
                    xp=?
                WHERE user_id=?
                AND species=?""",
                (
                    level,
                    xp,
                    user_id,
                    species
                )
            )

        result[
            "level"
        ]=level

        result[
            "gained"
        ]=(
            int(
                result.get(
                    "gained",
                    0
                )
            )
            +gained
        )

        result[
            "pet_xp_bonus"
        ]=amount

    def feed(
        user_id,
        guild_id
    ):
        result=old_feed(
            user_id,
            guild_id
        )

        addxp(
            result,
            12
        )

        return result

    def play(
        user_id,
        guild_id
    ):
        result=old_play(
            user_id,
            guild_id
        )

        addxp(
            result,
            15
        )

        if result.get(
            "ok"
        ):
            result[
                "buff"
            ]=activate(
                user_id,
                result[
                    "pet"
                ][
                    "species"
                ]
            )

        return result

    def explore(
        user_id,
        guild_id
    ):
        result=old_explore(
            user_id,
            guild_id
        )

        if not result.get(
            "ok"
        ):
            return result

        addxp(
            result,
            12
        )

        extra=bonus(
            user_id,
            "pet",
            result[
                "reward"
            ]
        )

        if extra:
            database.walletadd(
                guild_id,
                user_id,
                roses=extra
            )

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

        result[
            "pet_bonus"
        ]=extra

        buff=get(
            user_id
        )

        if (
            result.get(
                "discovery"
            ) is None
            and buff
            and int(
                buff.get(
                    "find_bonus",
                    0
                )
            )>0
            and secrets.randbelow(
                9200
            )<int(
                buff[
                    "find_bonus"
                ]
            )
        ):
            species=result[
                "pet"
            ][
                "species"
            ]

            with pet.connect() as con:
                got={
                    row[0]
                    for row in con.execute(
                        """SELECT item
                        FROM pet_finds
                        WHERE user_id=?
                        AND species=?""",
                        (
                            user_id,
                            species
                        )
                    ).fetchall()
                }

                missing=[
                    item
                    for item in pet.SPECIES[
                        species
                    ][
                        "finds"
                    ]
                    if item not in got
                ]

                if missing:
                    item=secrets.choice(
                        missing
                    )

                    con.execute(
                        """INSERT OR IGNORE INTO pet_finds(
                            user_id,
                            species,
                            item,
                            found_at
                        ) VALUES(?,?,?,?)""",
                        (
                            user_id,
                            species,
                            item,
                            time.time()
                        )
                    )

                    result[
                        "discovery"
                    ]=item

                    result[
                        "new"
                    ]=True

        return result

    def note(
        result,
        kind
    ):
        text=old_note(
            result,
            kind
        )

        if result.get(
            "pet_xp_bonus"
        ):
            buff=get(
                result[
                    "pet"
                ][
                    "user_id"
                ]
            )

            if buff:
                text+=(
                    f"\n{buff['emoji']} "
                    f"{buff['label']} ⊹ "
                    f"**+{result['pet_xp_bonus']} xp**"
                )

        if (
            kind=="play"
            and result.get(
                "buff"
            )
        ):
            buff=result[
                "buff"
            ]

            text+=(
                f"\n\n✦ **{buff['label']}**\n"
                f"{buff['text']} ⊹ "
                f"<t:{int(buff['expires_at'])}:R>"
            )

        if (
            kind=="explore"
            and result.get(
                "pet_bonus"
            )
        ):
            buff=get(
                result[
                    "pet"
                ][
                    "user_id"
                ]
            )

            if buff:
                text+=(
                    f"\n{buff['emoji']} "
                    f"{buff['label']} ⊹ "
                    f"**+{result['pet_bonus']:,} "
                    f"roses {rosieemoji.ROSE}**"
                )

        return text

    def panel(
        user_id,
        note=None
    ):
        return old_panel(user_id,note)

    pet.do_feed=feed
    pet.do_play=play
    pet.do_explore=explore
    pet.action_note=note
    pet.panel=panel
    pet._petbuff_patch=True

def patch_pluck():
    pluck=importlib.import_module(
        "commands.pluck"
    )

    if getattr(
        pluck,
        "_petbuff_patch",
        False
    ):
        return

    old_pluck=pluck.pluck
    old_embed=pluck.embed

    def run(
        user_id,
        guild_id
    ):
        result=old_pluck(
            user_id,
            guild_id
        )

        if not result.get(
            "ok"
        ):
            return result

        extra=bonus(
            user_id,
            "pluck",
            result[
                "value"
            ]
        )

        if extra:
            database.walletadd(
                guild_id,
                user_id,
                roses=extra
            )

        result[
            "pet_bonus"
        ]=extra

        result[
            "pet_buff"
        ]=(
            get(
                user_id
            )
            if extra
            else None
        )

        return result

    def embed(
        result
    ):
        out=old_embed(
            result
        )

        if result.get(
            "pet_bonus"
        ):
            buff=result.get(
                "pet_buff"
            )

            if buff:
                out.description=(
                    out.description
                    or ""
                )+(
                    f"\n{buff['emoji']} "
                    f"{buff['label']} ⊹ "
                    f"**+{result['pet_bonus']:,} "
                    f"roses {rosieemoji.ROSE}**"
                )

        return out

    pluck.pluck=run
    pluck.embed=embed
    pluck._petbuff_patch=True

def patch_garden():
    garden=importlib.import_module(
        "commands.garden"
    )

    if getattr(
        garden,
        "_petbuff_patch",
        False
    ):
        return

    old_harvest=garden.harvest
    old_embed=garden.harvest_embed

    def harvest(
        user_id,
        guild_id
    ):
        result=old_harvest(
            user_id,
            guild_id
        )

        if result.get(
            "ok"
        ):
            extra=0

            for wallet_guild,amount in result.get(
                "wallet_profit",
                {}
            ).items():
                value=bonus(
                    user_id,
                    "garden",
                    amount
                )

                if value:
                    database.walletadd(
                        int(
                            wallet_guild
                        ),
                        user_id,
                        roses=value
                    )

                    extra+=value

            result[
                "pet_bonus"
            ]=extra

            result[
                "pet_buff"
            ]=(
                get(
                    user_id
                )
                if extra
                else None
            )

        return result

    def embed(
        result
    ):
        out=old_embed(
            result
        )

        if result.get(
            "pet_bonus"
        ):
            buff=result.get(
                "pet_buff"
            )

            if buff:
                out.description=(
                    out.description
                    or ""
                )+(
                    f"\n{buff['emoji']} "
                    f"{buff['label']} ⊹ "
                    f"**+{result['pet_bonus']:,} "
                    f"roses {rosieemoji.ROSE}**"
                )

        return out

    garden.harvest=harvest
    garden.harvest_embed=embed
    garden._petbuff_patch=True

def patch_marriage():
    marriage=importlib.import_module(
        "commands.marriage"
    )

    if getattr(
        marriage,
        "_petbuff_patch",
        False
    ):
        return

    old_claim=marriage.claim

    def claim(marriage_id):
        result=old_claim(
            marriage_id
        )

        if not result.get("ok"):
            return result

        bonuses={}

        for user_id in (
            result["user1"],
            result["user2"]
        ):
            extra=bonus(
                user_id,
                "marriage",
                result["each"]
            )

            if extra:
                database.walletadd(
                    result["guild_id"],
                    user_id,
                    roses=extra
                )

                bonuses[
                    user_id
                ]=extra

        result[
            "pet_bonuses"
        ]=bonuses

        return result

    marriage.claim=claim
    marriage._petbuff_patch=True

def patch_boss():
    boss=importlib.import_module(
        "commands.boss"
    )

    if getattr(
        boss,
        "_petbuff_patch",
        False
    ):
        return

    old_damage=boss.damage
    old_act=boss.act

    current=ContextVar(
        "rosie_pet_boss_user",
        default=None
    )

    extra=ContextVar(
        "rosie_pet_boss_bonus",
        default=0
    )

    def damage(action,correct):
        dealt,status=old_damage(
            action,
            correct
        )

        user_id=current.get()

        amount=(
            bonus(
                user_id,
                "boss",
                dealt
            )
            if user_id
            else 0
        )

        extra.set(amount)

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
        user_token=current.set(
            user_id
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

            if result.get("ok"):
                result[
                    "pet_bonus"
                ]=extra.get()

            return result

        finally:
            current.reset(
                user_token
            )

            extra.reset(
                bonus_token
            )

    async def go(
        self,
        it,
        action
    ):
        result=boss.act(
            it.guild.id,
            it.message.id,
            it.user.id,
            action
        )

        if not result["ok"]:
            if (
                result["reason"]
                =="cooldown"
            ):
                await it.response.send_message(
                    f"hands off babe ⊹ "
                    f"<t:{int(result['ready'])}:R>",
                    ephemeral=True
                )
                return

            data=result.get(
                "game"
            )

            if data:
                await it.response.edit_message(
                    embed=boss.over(
                        data
                    ),
                    view=boss.BossView(
                        self.bot,
                        True
                    )
                )
            else:
                await it.response.send_message(
                    "mimic is dead",
                    ephemeral=True
                )

            return

        data=result["game"]

        if result["won"]:
            await it.response.edit_message(
                embed=boss.over(
                    data
                ),
                view=boss.BossView(
                    self.bot,
                    True
                )
            )
        else:
            await it.response.edit_message(
                embed=boss.live(
                    data
                ),
                view=self
            )

        amount=result.get(
            "pet_bonus",
            0
        )

        base=max(
            0,
            result["damage"]-amount
        )

        if (
            result["status"]
            =="bitten"
        ):
            text=(
                "mimic bit ur hand 💔 "
                "⊹ 0 dmg"
            )
        else:
            text=f"+{base:,} dmg"

            if amount:
                text+=(
                    f"\n👻 possession ⊹ "
                    f"**+{amount:,} dmg**"
                )

            if result["won"]:
                text+="\nu killed it"

        await it.followup.send(
            text,
            ephemeral=True
        )

    boss.damage=damage
    boss.act=act
    boss.BossView.go=go
    boss._petbuff_patch=True

def patch_blackjack():
    blackjack=importlib.import_module(
        "commands.blackjack"
    )

    if getattr(
        blackjack,
        "_petbuff_patch",
        False
    ):
        return

    old_start=blackjack.start

    def settle(con,data):
        blackjack.dealerplay(
            data
        )

        player=blackjack.score(
            data["player"]
        )[0]

        dealer=blackjack.score(
            data["dealer"]
        )[0]

        if player>21:
            return blackjack.save(
                con,
                data,
                "bust",
                0
            )

        if (
            dealer>21
            or player>dealer
        ):
            base=data["bet"]

            extra=bonus(
                data["user_id"],
                "casino",
                base
            )

            payout=(
                data["bet"]*2
                +extra
            )

            blackjack.casino.credit_con(
                con,
                data["guild_id"],
                data["user_id"],
                payout
            )

            return blackjack.save(
                con,
                data,
                "won",
                payout
            )

        if player==dealer:
            payout=data["bet"]

            blackjack.casino.credit_con(
                con,
                data["guild_id"],
                data["user_id"],
                payout
            )

            return blackjack.save(
                con,
                data,
                "push",
                payout
            )

        return blackjack.save(
            con,
            data,
            "lost",
            0
        )

    def start(guild_id,user_id,bet):
        result=old_start(
            guild_id,
            user_id,
            bet
        )

        if (
            not result.get("ok")
            or result[
                "game"
            ]["status"]!="blackjack"
        ):
            return result

        data=result["game"]
        base=bet*3//2

        extra=bonus(
            user_id,
            "casino",
            base
        )

        target=(
            bet
            +base
            +extra
        )

        extra_pay=max(
            0,
            target-data["payout"]
        )

        if extra_pay:
            with blackjack.casino.connect(
                True
            ) as con:
                con.execute(
                    "BEGIN IMMEDIATE"
                )

                blackjack.casino.credit_con(
                    con,
                    guild_id,
                    user_id,
                    extra_pay
                )

                con.execute(
                    "UPDATE blackjack_games "
                    "SET payout=? "
                    "WHERE id=?",
                    (
                        target,
                        data["id"]
                    )
                )

            data[
                "payout"
            ]=target

        return result

    def resultline(data):
        status=data["status"]

        if status=="active":
            return ""

        if status=="blackjack":
            base=data["bet"]*3//2

            extra=max(
                0,
                data["payout"]
                -data["bet"]
                -base
            )

            text=(
                f'\n\n**blackjack** ⊹ +{base:,} roses {rosieemoji.ROSE}'
            )

            if extra:
                text+=(
                    f"\n{(get(data['user_id']) or {'emoji':'🐾','label':'pet perk'})['emoji']} "
                    f"{(get(data['user_id']) or {'emoji':'🐾','label':'pet perk'})['label']} ⊹ "
                    f"**+{extra:,} roses {rosieemoji.ROSE}**" 
                )

            return text

        if status=="won":
            base=data["bet"]

            extra=max(
                0,
                data["payout"]
                -data["bet"]
                -base
            )

            text=(
                f'\n\n**won** ⊹ +{base:,} roses {rosieemoji.ROSE}'
            )

            if extra:
                text+=(
                    f"\n{(get(data['user_id']) or {'emoji':'🐾','label':'pet perk'})['emoji']} "
                    f"{(get(data['user_id']) or {'emoji':'🐾','label':'pet perk'})['label']} ⊹ "
                    f"**+{extra:,} roses {rosieemoji.ROSE}**" 
                )

            return text

        if status=="push":
            return "\n\n**push**"

        if status=="bust":
            return "\n\n**bust**"

        if (
            status
            =="dealer_blackjack"
        ):
            return (
                "\n\n**dealer blackjack**"
            )

        return "\n\n**dealer wins**"

    blackjack.settle=settle
    blackjack.start=start
    blackjack.resultline=resultline
    blackjack._petbuff_patch=True

def install():
    init()
    patch_pet()
    patch_pluck()
    patch_garden()
    patch_marriage()
    patch_boss()
    patch_blackjack()
