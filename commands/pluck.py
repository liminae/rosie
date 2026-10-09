import secrets
import sqlite3
import time

import discord
from core import database
from core import game
from discord import app_commands
from discord.ext import commands
from core import emoji as rosieemoji

COOLDOWN=600
LIMIT=50
ROSACEA_TIME=86400
ROSACEA_COST=1000
ROSEOLA_COST=2500
IMMUNITY=86400
OUTCOMES=(
    (7000,"rose",rosieemoji.ROSE,"rose",50),
    (2000,"pretty",rosieemoji.ROSE,"pretty rose",75),
    (700,"perfect","✦","perfect rose",125),
    (200,"bouquet","💐","little bouquet",250),
    (80,"blood","🩸","blood rose",500),
    (20,"golden","✦","GOLDEN ROSE",2000)
)
MESSAGES={
    "rose":("fresh from the bush.","normal one. shocking.","rosie approves.","clean pluck hehe"),
    "pretty":("okay she's cute.","this one was showing off.","prettier than the last one ngl","not bad at all."),
    "perfect":("not a petal out of place.","oh this one is kinda perfect.","rosie inspected it twice.","somebody frame this one."),
    "bouquet":("u grabbed half the bush somehow.","okayyy greedy.","one pluck btw.","the bush surrendered."),
    "blood":("that was not red when u grabbed it.","this one is wet. do not ask.","maybe put that down actually.","the stem is staring back."),
    "golden":("oh????","THE BUSH LOVES U","rosie just stared at it for a second.","yeah no keep that one.")
}
SICK={
    "rosacea":("the rash appears delighted.",'rosacea says hi ' + rosieemoji.ROSE,"the rose recognized one of its own.","ur skin is matching the inventory now.","rosie says stop scratching."),
    "roseola":("roseola remains committed to the bit.","you look contagious. spiritually.","this is what happens when u keep touching the bush.","the flower seems healthier than you.","rosie has begun referring to u as patient zero."),
    "after":("the symptoms are gone. the humiliation is not.","rosie is still calling you diseased btw.","the rash left but its legacy remains.","you look better. allegedly.")
}

def connect():
    con=sqlite3.connect(database.FILE,timeout=10)
    con.row_factory=sqlite3.Row
    return con

def init():
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS pluck_users(
            user_id INTEGER PRIMARY KEY,
            total INTEGER NOT NULL DEFAULT 0,
            roses INTEGER NOT NULL DEFAULT 0,
            blood INTEGER NOT NULL DEFAULT 0,
            golden INTEGER NOT NULL DEFAULT 0,
            pricks INTEGER NOT NULL DEFAULT 0,
            rosacea INTEGER NOT NULL DEFAULT 0,
            roseola INTEGER NOT NULL DEFAULT 0,
            disease TEXT,
            infected_at REAL,
            after_until REAL NOT NULL DEFAULT 0,
            last_pluck REAL NOT NULL DEFAULT 0
        )""")
        cols={row[1] for row in con.execute("PRAGMA table_info(pluck_users)")}
        if "rosacea_plucks" not in cols:
            con.execute("ALTER TABLE pluck_users ADD COLUMN rosacea_plucks INTEGER NOT NULL DEFAULT 0")
        if "immune_until" not in cols:
            con.execute("ALTER TABLE pluck_users ADD COLUMN immune_until REAL NOT NULL DEFAULT 0")
        con.execute("""CREATE TABLE IF NOT EXISTS pluck_days(
            user_id INTEGER NOT NULL,
            day TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id,day)
        )""")

def touch(con,user_id):
    con.execute("INSERT OR IGNORE INTO pluck_users(user_id) VALUES(?)",(user_id,))
    con.execute("INSERT OR IGNORE INTO pluck_days(user_id,day) VALUES(?,?)",(user_id,game.day().isoformat()))

def sick(con,user_id,now=None):
    now=now or time.time()
    touch(con,user_id)
    row=con.execute("SELECT * FROM pluck_users WHERE user_id=?",(user_id,)).fetchone()
    if row["disease"]=="rosacea" and row["infected_at"] and now>=row["infected_at"]+ROSACEA_TIME:
        con.execute("UPDATE pluck_users SET disease=NULL,infected_at=NULL,after_until=?,rosacea_plucks=0 WHERE user_id=?",(now+7200,user_id))
        row=con.execute("SELECT * FROM pluck_users WHERE user_id=?",(user_id,)).fetchone()
    return dict(row)

def roll():
    n=secrets.randbelow(10000)
    for chance,key,emoji,name,value in OUTCOMES:
        if n<chance:
            return key,emoji,name,value
        n-=chance
    raise RuntimeError("pluck odds died")

def danger(n):
    if n<=3:
        return 300
    if n<=6:
        return 500
    if n<=9:
        return 1000
    return 2000

def pluck(user_id,guild_id):
    now=time.time()
    today=game.day().isoformat()
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        touch(con,user_id)
        row=sick(con,user_id,now)
        cooldown=900 if row["disease"]=="roseola" else COOLDOWN
        ready=row["last_pluck"]+cooldown
        if now<ready:
            return {"ok":False,"reason":"cooldown","ready":ready}
        day=con.execute("SELECT count FROM pluck_days WHERE user_id=? AND day=?",(user_id,today)).fetchone()
        count=day["count"] if day else 0
        if count>=LIMIT:
            return {"ok":False,"reason":"cap","reset":game.next_reset().timestamp()}
        key,emoji,name,value=roll()
        prick=secrets.randbelow(10000)<(3000 if key=="blood" else 500)
        disease=row["disease"]
        infected=row["infected_at"]
        after=row["after_until"] or 0
        rosacea_plucks=int(row["rosacea_plucks"] or 0)
        new=None
        if disease is None and now>=float(row["immune_until"] or 0) and prick and secrets.randbelow(10000)<1500:
            disease="rosacea"
            infected=now
            after=0
            rosacea_plucks=0
            new="rosacea"
        elif disease=="rosacea":
            rosacea_plucks+=1
            if secrets.randbelow(10000)<danger(rosacea_plucks):
                disease="roseola"
                infected=now
                after=0
                rosacea_plucks=0
                new="roseola"
        else:
            rosacea_plucks=0
        if disease=="roseola":
            value//=2
        con.execute("INSERT OR IGNORE INTO wallets(guild_id,user_id) VALUES(?,?)",(guild_id,user_id))
        con.execute("UPDATE wallets SET roses=roses+? WHERE guild_id=? AND user_id=?",(value,guild_id,user_id))
        con.execute("UPDATE pluck_days SET count=count+1 WHERE user_id=? AND day=?",(user_id,today))
        con.execute("""UPDATE pluck_users SET
            total=total+1,
            roses=roses+?,
            blood=blood+?,
            golden=golden+?,
            pricks=pricks+?,
            rosacea=rosacea+?,
            roseola=roseola+?,
            disease=?,
            infected_at=?,
            after_until=?,
            rosacea_plucks=?,
            last_pluck=?
            WHERE user_id=?""",(
            value,
            int(key=="blood"),
            int(key=="golden"),
            int(prick),
            int(new=="rosacea"),
            int(new=="roseola"),
            disease,
            infected,
            after,
            rosacea_plucks,
            now,
            user_id
        ))
        return {
            "ok":True,
            "key":key,
            "emoji":emoji,
            "name":name,
            "value":value,
            "count":count+1,
            "ready":now+(900 if disease=="roseola" else COOLDOWN),
            "prick":prick,
            "disease":disease,
            "new":new,
            "after":after
        }

def cure(user_id,guild_id):
    now=time.time()
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        row=sick(con,user_id,now)
        disease=row["disease"]
        if disease is None:
            return {"ok":False,"reason":"fine"}
        cost=ROSEOLA_COST if disease=="roseola" else ROSACEA_COST
        con.execute("INSERT OR IGNORE INTO wallets(guild_id,user_id) VALUES(?,?)",(guild_id,user_id))
        roses=con.execute("SELECT roses FROM wallets WHERE guild_id=? AND user_id=?",(guild_id,user_id)).fetchone()[0]
        if roses<cost:
            return {"ok":False,"reason":"broke","need":cost-roses,"cost":cost,"disease":disease}
        linger=21600 if disease=="roseola" else 7200
        con.execute("UPDATE wallets SET roses=roses-? WHERE guild_id=? AND user_id=?",(cost,guild_id,user_id))
        con.execute("UPDATE pluck_users SET disease=NULL,infected_at=NULL,after_until=?,rosacea_plucks=0,immune_until=? WHERE user_id=?",(now+linger,now+IMMUNITY,user_id))
        return {"ok":True,"cost":cost,"disease":disease,"linger":linger,"immune_until":now+IMMUNITY}

def stats(user_id):
    with connect() as con:
        row=sick(con,user_id)
        day=con.execute("SELECT count FROM pluck_days WHERE user_id=? AND day=?",(user_id,game.day().isoformat())).fetchone()
    row["today"]=day["count"] if day else 0
    row["cooldown"]=900 if row["disease"]=="roseola" else COOLDOWN
    row["ready"]=row["last_pluck"]+row["cooldown"]
    return row

def line(key):
    return secrets.choice(MESSAGES[key])

def embed(result):
    title=f"{result['emoji']} {result['name']}"
    parts=[line(result["key"]),""]

    if result["key"]=="golden":
        parts.extend([
            f"**+{result['value']:,} roses {rosieemoji.ROSE}**",
            "odds ⊹ **0.2%**"
        ])
    else:
        parts.append(f"plucked ⊹ **+{result['value']:,} roses {rosieemoji.ROSE}**")

    parts.extend([
        f"today ⊹ **{result['count']} / {LIMIT}**",
        f"next ⊹ <t:{int(result['ready'])}:R>"
    ])

    if result["prick"]:
        parts.extend([
            "",
            "🩸 **ow.**",
            "a thorn got u"
        ])

    if result["new"]=="rosacea":
        parts.extend([
            "",
            rosieemoji.ROSE + ' **you contracted Rosacea**',
            "maybe stop grabbing roses barehanded idiot",
            'clears ⊹ in 24 hours • cure ⊹ 1,000 ' + rosieemoji.ROSE
        ])
    elif result["new"]=="roseola":
        parts.extend([
            "",
            "🥀 **oh girl.**",
            "Rosacea turned into **Roseola**",
            "continuing to touch the roses was apparently not treatment",
            'Roseola stays until you pay **2,500 roses ' + rosieemoji.ROSE + '** to cure it',
            "plucking ⊹ **-50% roses • 15 minute cooldown**"
        ])
    elif result["disease"]=="roseola" and secrets.randbelow(100)<70:
        parts.extend(["",secrets.choice(SICK["roseola"])])
    elif result["disease"]=="rosacea" and secrets.randbelow(100)<40:
        parts.extend(["",secrets.choice(SICK["rosacea"])])
    elif result["after"]>time.time() and secrets.randbelow(100)<30:
        parts.extend(["",secrets.choice(SICK["after"])])

    if result["count"]>=LIMIT:
        parts.extend([
            "",
            "🌱 **patch picked clean**",
            "more roses tomorrow babe"
        ])

    return discord.Embed(
        title=title,
        description="\n".join(parts),
        color=discord.Color.dark_red()
    )

class CureView(discord.ui.View):
    def __init__(self,user_id,disease,guild_id):
        super().__init__(timeout=180)
        self.user_id=user_id
        self.guild_id=guild_id

    @discord.ui.button(
        emoji="💊",
        style=discord.ButtonStyle.secondary
    )
    async def heal(self,it:discord.Interaction,button:discord.ui.Button):
        if it.user.id!=self.user_id:
            await it.response.send_message(
                "not ur disease babe",
                ephemeral=True
            )
            return

        result=cure(it.user.id,self.guild_id)

        if not result["ok"]:
            if result["reason"]=="broke":
                await it.response.send_message(
                    f"broke patient you need {result['need']:,} more {rosieemoji.ROSE}",
                    ephemeral=True
                )
            else:
                await it.response.send_message(
                    "ur already fine somehow",
                    ephemeral=True
                )
            return

        hours=result["linger"]//3600

        await it.response.send_message(
            f"cured **{result['disease']}** ⊹ -{result['cost']:,} roses {rosieemoji.ROSE}\nrosie may continue bullying u for {hours}h\nprotected ⊹ <t:{int(result['immune_until'])}:R>",
            ephemeral=True
        )

class Pluck(commands.Cog):
    @app_commands.command(
        name="pluck",
        description="pluck roses from the patch"
    )
    @app_commands.guild_only()
    @app_commands.choices(action=[
        app_commands.Choice(name="cure",value="cure")
    ])
    async def pluck(
        self,
        it:discord.Interaction,
        action:app_commands.Choice[str]|None=None
    ):
        game.touch(it.user.id)

        if action is not None:
            result=cure(it.user.id,it.guild_id)

            if not result["ok"]:
                if result["reason"]=="broke":
                    await it.response.send_message(
                        f"broke patient you need {result['need']:,} more {rosieemoji.ROSE}",
                        ephemeral=True
                    )
                else:
                    await it.response.send_message(
                        "ur not sick rn",
                        ephemeral=True
                    )
                return

            hours=result["linger"]//3600

            await it.response.send_message(
                f"💊 cured **{result['disease']}** ⊹ -{result['cost']:,} roses {rosieemoji.ROSE}\nrosie may continue bullying u for {hours}h\nprotected ⊹ <t:{int(result['immune_until'])}:R>",
                ephemeral=True
            )
            return

        result=pluck(it.user.id,it.guild_id)

        if not result["ok"]:
            if result["reason"]=="cooldown":
                await it.response.send_message(
                    f"hands off the bush\n"
                    f"ready ⊹ <t:{int(result['ready'])}:R>",
                    ephemeral=True
                )
            else:
                await it.response.send_message(
                    f"patch is picked clean 🌱\n"
                    f"more roses ⊹ <t:{int(result['reset'])}:R>",
                    ephemeral=True
                )
            return

        view=(
            CureView(it.user.id,result["disease"],it.guild_id)
            if result["disease"]
            else None
        )

        await it.response.send_message(
            embed=embed(result),
            **({"view":view} if view is not None else {})
        )

async def setup(bot):
    init()
    await bot.add_cog(Pluck())
