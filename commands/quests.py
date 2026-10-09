import hashlib
import json
import sqlite3

import discord
from core import database
from core import game
from discord import app_commands
from discord.ext import commands
from core import emoji as rosieemoji

QUEST_REWARD=100
CLEAR_REWARD=200
QUESTS={
    "daily":(rosieemoji.ROSE,"pick today's roses",1),
    "scratch":("🎟️","finish today's scratch",1),
    "plant3":("🌱","plant 3 crops",3),
    "harvest3":("✂️","harvest 3 crops",3),
    "plant5":("🌱","plant 5 crops",5),
    "harvest5":("✂️","harvest 5 crops",5),
    "pluck3":(rosieemoji.ROSE,"pluck 3 roses",3),
    "box":("📦","open a mystery box",1)
}

def connect():
    con=sqlite3.connect(database.FILE)
    con.row_factory=sqlite3.Row
    return con

def gconnect():
    con=sqlite3.connect(game.DB,timeout=10)
    con.row_factory=sqlite3.Row
    return con

def init():
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS quest_days(
            user_id INTEGER NOT NULL,
            day TEXT NOT NULL,
            quests TEXT NOT NULL,
            claimed TEXT NOT NULL DEFAULT '[]',
            clear_claimed INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id,day)
        )""")

def garden(user_id):
    today=game.day().isoformat()
    try:
        with gconnect() as con:
            found=con.execute(
                "SELECT planted,harvested FROM garden_v2_daily "
                "WHERE user_id=? AND day=?",
                (user_id,today)
            ).fetchone()
        return (
            dict(found)
            if found
            else {"planted":0,"harvested":0}
        )
    except sqlite3.OperationalError:
        return {"planted":0,"harvested":0}

def plucks(user_id):
    today=game.day().isoformat()
    with connect() as con:
        try:
            found=con.execute(
                "SELECT count FROM pluck_days "
                "WHERE user_id=? AND day=?",
                (user_id,today)
            ).fetchone()
        except sqlite3.OperationalError:
            return 0
    return found[0] if found else 0

def boxes(user_id):
    now=game.now()
    start=now.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0
    ).timestamp()
    end=game.next_reset().timestamp()

    with connect() as con:
        found=con.execute(
            "SELECT COUNT(*) FROM opens "
            "WHERE user=? AND time>=? AND time<?",
            (user_id,int(start),int(end))
        ).fetchone()

    return found[0]

def progress(user_id,key):
    if key=="daily":
        return int(game.has_daily(user_id))

    if key=="scratch":
        state=game.scratch_state(user_id)
        return int(bool(state and state["finished"]))

    if key=="pluck3":
        return plucks(user_id)

    day=garden(user_id)

    if key in ("plant3","plant5"):
        return day["planted"]

    if key in ("harvest3","harvest5"):
        return day["harvested"]

    if key=="box":
        return boxes(user_id)

    return 0

def pick(user_id,guild_id):
    today=game.day().isoformat()
    roses,rings=database.wallet(guild_id,user_id)
    seed=int.from_bytes(
        hashlib.sha256(
            f"rosie:quests:{today}:{user_id}".encode()
        ).digest()[:8],
        "big"
    )

    first=("daily","scratch")[seed%2]
    second=("plant3","harvest3")[(seed//2)%2]
    third_pool=["plant5","harvest5","pluck3"]

    if roses>=2000 or boxes(user_id)>0:
        third_pool.append("box")

    third=third_pool[(seed//4)%len(third_pool)]

    return [first,second,third]

def decode(found):
    data=dict(found)
    data["quests"]=json.loads(data["quests"])
    data["claimed"]=json.loads(data["claimed"])
    return data

def ensure(user_id,guild_id):
    today=game.day().isoformat()

    with connect() as con:
        found=con.execute(
            "SELECT * FROM quest_days "
            "WHERE user_id=? AND day=?",
            (user_id,today)
        ).fetchone()

        if found is None:
            con.execute(
                "INSERT INTO quest_days(user_id,day,quests) "
                "VALUES(?,?,?)",
                (user_id,today,json.dumps(pick(user_id,guild_id)))
            )

            found=con.execute(
                "SELECT * FROM quest_days "
                "WHERE user_id=? AND day=?",
                (user_id,today)
            ).fetchone()

    return decode(found)

def state(user_id,guild_id):
    data=ensure(user_id,guild_id)
    items=[]

    for key in data["quests"]:
        emoji,label,target=QUESTS[key]
        value=min(progress(user_id,key),target)

        items.append({
            "key":key,
            "label":f"{emoji} {label}",
            "target":target,
            "value":value,
            "done":value>=target,
            "claimed":key in data["claimed"]
        })

    return data,items

def claim(user_id,guild_id):
    today=game.day().isoformat()
    data,items=state(user_id,guild_id)
    completed={
        item["key"]
        for item in items
        if item["done"]
    }

    with connect() as con:
        con.execute("BEGIN IMMEDIATE")

        found=con.execute(
            "SELECT claimed,clear_claimed FROM quest_days "
            "WHERE user_id=? AND day=?",
            (user_id,today)
        ).fetchone()

        claimed=set(json.loads(found["claimed"]))
        new=completed-claimed
        amount=len(new)*QUEST_REWARD
        claimed|=new
        clear=(
            len(claimed)==3
            and not found["clear_claimed"]
        )

        if clear:
            amount+=CLEAR_REWARD

        if amount:
            con.execute(
                "INSERT OR IGNORE INTO wallets(guild_id,user_id) VALUES(?,?)",
                (guild_id,user_id)
            )

            con.execute(
                "UPDATE wallets SET roses=roses+? WHERE guild_id=? AND user_id=?",
                (amount,guild_id,user_id)
            )

            con.execute(
                "UPDATE quest_days "
                "SET claimed=?,clear_claimed=? "
                "WHERE user_id=? AND day=?",
                (
                    json.dumps(sorted(claimed)),
                    int(found["clear_claimed"] or clear),
                    user_id,
                    today
                )
            )

        return {
            "amount":amount,
            "clear":clear
        }

def embed(user_id,name,guild_id):
    data,items=state(user_id,guild_id)
    lines=[]

    for item in items:
        icon="✅" if item["done"] else "◻️"
        progress_text=(
            ""
            if item["target"]==1
            else f"\n{item['value']} / {item['target']}"
        )
        reward=(
            "claimed"
            if item["claimed"]
            else f'{QUEST_REWARD} roses {rosieemoji.ROSE}'
        )

        lines.append(
            f"{icon} {item['label']}"
            f"{progress_text}\n"
            f"⊹ {reward}"
        )

    clear=(
        "claimed"
        if data["clear_claimed"]
        else f'{CLEAR_REWARD} roses {rosieemoji.ROSE}'
    )

    reset=int(game.next_reset().timestamp())

    return discord.Embed(
        title=f"📜 {name}'s quests",
        description=(
            "\n\n".join(lines)
            +f"\n\n**all clear**\n"
            f"⊹ {clear}\n\n"
            f"resets ⊹ <t:{reset}:R>"
        ),
        color=discord.Color.dark_red()
    )

class QuestView(discord.ui.View):
    def __init__(self,user_id,name,guild_id):
        super().__init__(timeout=300)
        self.user_id=user_id
        self.name=name
        self.guild_id=guild_id

    @discord.ui.button(
        emoji=rosieemoji.ROSE,
        style=discord.ButtonStyle.danger
    )
    async def claim(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        if it.user.id!=self.user_id:
            await it.response.send_message(
                "make ur own /quests",
                ephemeral=True
            )
            return

        result=claim(it.user.id,self.guild_id)

        if not result["amount"]:
            await it.response.send_message(
                "nothing to claim",
                ephemeral=True
            )
            return

        text=(
            f"claimed ⊹ **{result['amount']:,} roses {rosieemoji.ROSE}**"
        )

        if result["clear"]:
            text+="\nall clear ✦"

        await it.response.edit_message(
            embed=embed(it.user.id,self.name,self.guild_id),
            view=QuestView(it.user.id,self.name,self.guild_id)
        )

        await it.followup.send(
            text,
            ephemeral=True
        )

    @discord.ui.button(
        emoji="🔄",
        style=discord.ButtonStyle.secondary
    )
    async def refresh(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        if it.user.id!=self.user_id:
            await it.response.send_message(
                "make ur own /quests",
                ephemeral=True
            )
            return

        await it.response.edit_message(
            embed=embed(it.user.id,self.name,self.guild_id),
            view=QuestView(it.user.id,self.name,self.guild_id)
        )

class Quests(commands.Cog):
    @app_commands.command(
        name="quests",
        description="see today's quests"
    )
    @app_commands.guild_only()
    async def quests(self,it:discord.Interaction):
        game.touch(it.user.id)
        ensure(it.user.id,it.guild_id)

        view=QuestView(
            it.user.id,
            it.user.display_name,
            it.guild_id
        )

        await it.response.send_message(
            embed=embed(
                it.user.id,
                it.user.display_name,
                it.guild_id
            ),
            view=view
        )

async def setup(bot):
    init()
    await bot.add_cog(Quests())
