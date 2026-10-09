import sqlite3
import time
from datetime import date,datetime,timedelta

import discord
from core import database
from core import fulfillment
from core import game
from core import guildconfig
from core import legacyconfig
from discord import app_commands
from discord.ext import commands,tasks
from discord.http import Route
from .redeem import RedeemView
from core import emoji as rosieemoji

REFRESH_COST=1
PING_ROLE="Drop Ping ⋆‧°𓏲ּ𝄢"
REWARDS={
    "roses":(rosieemoji.ROSE,"roses"),
    "rings":("💍","rings"),
    "nitro_basic":("💙","nitro basic • 1 month"),
    "nitro":("💜","nitro • 1 month"),
    "steam_game":("🎮","steam game")
}
DEFAULT_AMOUNT={"roses":5000,"rings":1,"nitro_basic":1,"nitro":1,"steam_game":1}

def connect():
    con=sqlite3.connect(database.FILE)
    con.row_factory=sqlite3.Row
    return con

def init():
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS drop_stock(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            target_guild_id INTEGER,
            channel_id INTEGER NOT NULL,
            message_id INTEGER,
            reward TEXT NOT NULL,
            amount INTEGER NOT NULL,
            price INTEGER NOT NULL DEFAULT 0,
            ring_price INTEGER NOT NULL DEFAULT 0,
            stock INTEGER NOT NULL,
            remaining INTEGER NOT NULL,
            user_limit INTEGER NOT NULL,
            duration INTEGER NOT NULL,
            created_at REAL NOT NULL,
            start_at REAL,
            started_at REAL,
            ends_at REAL,
            status TEXT NOT NULL DEFAULT 'stocked'
        )""")
        cols={x[1] for x in con.execute("PRAGMA table_info(drop_stock)")}
        if "target_guild_id" not in cols:
            con.execute("ALTER TABLE drop_stock ADD COLUMN target_guild_id INTEGER")
        if "ring_price" not in cols:
            con.execute("ALTER TABLE drop_stock ADD COLUMN ring_price INTEGER NOT NULL DEFAULT 0")
        if "start_at" not in cols:
            con.execute("ALTER TABLE drop_stock ADD COLUMN start_at REAL")
        if "pinged_at" not in cols:
            con.execute("ALTER TABLE drop_stock ADD COLUMN pinged_at REAL")
        if "sold_out_at" not in cols:
            con.execute("ALTER TABLE drop_stock ADD COLUMN sold_out_at REAL")
        con.execute("""CREATE TABLE IF NOT EXISTS drop_buys_v2(
            drop_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(drop_id,user_id)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS drop_refresh(
            user_id INTEGER PRIMARY KEY,
            unlocked_at REAL NOT NULL
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS drop_snipe(
            slot INTEGER PRIMARY KEY,
            drop_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            guild_id INTEGER,
            armed_at REAL NOT NULL
        )""")
        snipecols={x[1] for x in con.execute("PRAGMA table_info(drop_snipe)")}
        if "guild_id" not in snipecols:
            con.execute("ALTER TABLE drop_snipe ADD COLUMN guild_id INTEGER")
        con.execute("""CREATE TABLE IF NOT EXISTS items(
            user INTEGER NOT NULL,
            item TEXT NOT NULL,
            amount INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user,item)
        )""")
        rows=con.execute("SELECT id,target_guild_id,start_at FROM drop_stock WHERE status='live' ORDER BY target_guild_id,id DESC").fetchall()
        seen=set()
        for old in rows:
            key=old["target_guild_id"]
            if key in seen:
                state="scheduled" if old["start_at"] is not None else "stocked"
                con.execute("UPDATE drop_stock SET status=?,started_at=NULL,ends_at=NULL WHERE id=?",(state,old["id"]))
            else:
                seen.add(key)

def row(found):
    return dict(found) if found else None

def get(drop_id):
    with connect() as con:
        found=con.execute("SELECT * FROM drop_stock WHERE id=?",(drop_id,)).fetchone()
    return row(found)

def migrateguild(guild_id):
    with connect() as con:
        con.execute("""UPDATE drop_snipe
        SET guild_id=COALESCE(
            (SELECT target_guild_id FROM drop_stock WHERE id=drop_snipe.drop_id),
            ?
        )
        WHERE guild_id IS NULL""",(guild_id,))

def arm(drop_id,user_id,guild_id):
    with connect() as con:
        con.execute("INSERT OR REPLACE INTO drop_snipe(slot,drop_id,user_id,guild_id,armed_at) VALUES(1,?,?,?,?)",(drop_id,user_id,guild_id,time.time()))

def armed(drop_id=None):
    with connect() as con:
        if drop_id is None:
            found=con.execute("SELECT * FROM drop_snipe WHERE slot=1").fetchone()
        else:
            found=con.execute("SELECT * FROM drop_snipe WHERE slot=1 AND drop_id=?",(drop_id,)).fetchone()
    return row(found)

def clear(drop_id=None):
    with connect() as con:
        if drop_id is None:
            con.execute("DELETE FROM drop_snipe WHERE slot=1")
        else:
            con.execute("DELETE FROM drop_snipe WHERE slot=1 AND drop_id=?",(drop_id,))

def live(guild_id=None):
    with connect() as con:
        if guild_id is None:
            found=con.execute("SELECT * FROM drop_stock WHERE status='live' ORDER BY id DESC LIMIT 1").fetchone()
        else:
            found=con.execute("SELECT * FROM drop_stock WHERE status='live' AND (target_guild_id IS NULL OR target_guild_id=?) ORDER BY target_guild_id IS NULL,id DESC LIMIT 1",(guild_id,)).fetchone()
    data=row(found)
    if data and (data["ends_at"]<=time.time() or data["remaining"]<=0):
        stop(data["id"])
        return None
    return data

def scheduled(guild_id=None):
    with connect() as con:
        if guild_id is None:
            rows=con.execute("SELECT * FROM drop_stock WHERE status='scheduled' ORDER BY start_at,id").fetchall()
        else:
            rows=con.execute("SELECT * FROM drop_stock WHERE status='scheduled' AND (target_guild_id IS NULL OR target_guild_id=?) ORDER BY start_at,id",(guild_id,)).fetchall()
    return [dict(x) for x in rows]

def stocks(guild_id=None):
    with connect() as con:
        if guild_id is None:
            rows=con.execute("SELECT * FROM drop_stock WHERE status='stocked' ORDER BY id").fetchall()
        else:
            rows=con.execute("SELECT * FROM drop_stock WHERE status='stocked' AND (target_guild_id IS NULL OR target_guild_id=?) ORDER BY id",(guild_id,)).fetchall()
    return [dict(x) for x in rows]

def due():
    with connect() as con:
        rows=con.execute("SELECT * FROM drop_stock WHERE status='scheduled' AND start_at<=? ORDER BY start_at,id",(time.time(),)).fetchall()
    return [dict(x) for x in rows]

def warnings():
    now=time.time()
    with connect() as con:
        rows=con.execute("""SELECT * FROM drop_stock
            WHERE status='scheduled'
            AND pinged_at IS NULL
            AND start_at>?
            AND start_at-600<=?
            ORDER BY start_at,id""",(now,now)).fetchall()
    return [dict(x) for x in rows]

def mark_ping(drop_id):
    with connect() as con:
        con.execute("UPDATE drop_stock SET pinged_at=? WHERE id=? AND pinged_at IS NULL",(time.time(),drop_id))

def lives():
    with connect() as con:
        rows=con.execute("SELECT * FROM drop_stock WHERE status='live' ORDER BY id").fetchall()
    return [dict(x) for x in rows]

def deletable(guild_id=None):
    with connect() as con:
        if guild_id is None:
            rows=con.execute("""SELECT * FROM drop_stock
                WHERE status IN ('live','scheduled','stocked')
                ORDER BY CASE status
                    WHEN 'live' THEN 0
                    WHEN 'scheduled' THEN 1
                    ELSE 2
                END,
                COALESCE(start_at,created_at),
                id""").fetchall()
        else:
            rows=con.execute("""SELECT * FROM drop_stock
                WHERE status IN ('live','scheduled','stocked')
                AND (target_guild_id IS NULL OR target_guild_id=?)
                ORDER BY CASE status
                    WHEN 'live' THEN 0
                    WHEN 'scheduled' THEN 1
                    ELSE 2
                END,
                COALESCE(start_at,created_at),
                id""",(guild_id,)).fetchall()
    return [dict(x) for x in rows]

def delete_drop(drop_id):
    with connect() as con:
        cur=con.execute("""UPDATE drop_stock
            SET status='deleted',
                ends_at=CASE WHEN status='live' THEN ? ELSE ends_at END
            WHERE id=? AND status IN ('live','scheduled','stocked')""",(time.time(),drop_id))
        if cur.rowcount==1:
            con.execute("DELETE FROM drop_snipe WHERE drop_id=?",(drop_id,))
        return cur.rowcount==1

def stock(guild_id,channel_id,reward,amount,rose_price,ring_price,total,limit,duration,start_at=None,target_guild_id=None):
    status="scheduled" if start_at is not None else "stocked"
    with connect() as con:
        cur=con.execute("""INSERT INTO drop_stock(
            guild_id,target_guild_id,channel_id,reward,amount,price,ring_price,stock,remaining,user_limit,duration,created_at,start_at,status
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(guild_id,target_guild_id,channel_id,reward,amount,rose_price,ring_price,total,total,limit,duration,time.time(),start_at,status))
        return cur.lastrowid

def start(drop_id,channel_id):
    now=time.time()
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        data=con.execute("SELECT * FROM drop_stock WHERE id=?",(drop_id,)).fetchone()
        if data is None or data["status"] not in ("stocked","scheduled"):
            return None
        target=data["target_guild_id"]
        if target is None:
            conflict=con.execute("SELECT 1 FROM drop_stock WHERE status='live' LIMIT 1").fetchone()
        else:
            conflict=con.execute("SELECT 1 FROM drop_stock WHERE status='live' AND (target_guild_id IS NULL OR target_guild_id=?) LIMIT 1",(target,)).fetchone()
        if conflict:
            return None
        con.execute("UPDATE drop_stock SET channel_id=?,status='live',started_at=?,ends_at=? WHERE id=?",(channel_id,now,now+data["duration"]*60,drop_id))
    return get(drop_id)

def stop(drop_id,status="ended"):
    with connect() as con:
        con.execute("UPDATE drop_stock SET status=? WHERE id=? AND status='live'",(status,drop_id))

def unlocked(user_id):
    with connect() as con:
        return con.execute("SELECT 1 FROM drop_refresh WHERE user_id=?",(user_id,)).fetchone() is not None

def unlock(guild_id,user_id):
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        if con.execute("SELECT 1 FROM drop_refresh WHERE user_id=?",(user_id,)).fetchone():
            return True
        con.execute("INSERT OR IGNORE INTO wallets(guild_id,user_id) VALUES(?,?)",(guild_id,user_id))
        rings=con.execute("SELECT rings FROM wallets WHERE guild_id=? AND user_id=?",(guild_id,user_id)).fetchone()[0]
        if rings<REFRESH_COST:
            return False
        con.execute("UPDATE wallets SET rings=rings-? WHERE guild_id=? AND user_id=?",(REFRESH_COST,guild_id,user_id))
        con.execute("INSERT INTO drop_refresh(user_id,unlocked_at) VALUES(?,?)",(user_id,time.time()))
        return True

def pingrole(guild):
    if guild is None:
        return None
    settings=guildconfig.get(guild.id)
    if settings and settings["drop_ping_role_id"]:
        return guild.get_role(settings["drop_ping_role_id"])
    legacy_id=legacyconfig.DROP_CHANNEL_ID
    if (
        not legacy_id
        or guild.get_channel(legacy_id) is None
    ):
        return None
    exact=discord.utils.get(guild.roles,name=PING_ROLE)
    if exact:
        return exact
    return next((role for role in guild.roles if "drop ping" in role.name.casefold()),None)

def pingson(guild):
    if guild is None:
        return False
    settings=guildconfig.get(guild.id)
    if settings and settings["drop_pings_enabled"] is not None:
        return bool(settings["drop_pings_enabled"])
    legacy_id=legacyconfig.DROP_CHANNEL_ID
    return bool(
        legacy_id
        and guild.get_channel(
            legacy_id
        ) is not None
        and pingrole(
            guild
        ) is not None
    )

def hasping(guild,user_id):
    if not pingson(guild):
        return False
    role=pingrole(guild)
    member=guild.get_member(user_id) if guild else None
    return bool(role and member and role in member.roles)

def buy(drop_id,guild_id,user_id,amount=None):
    now=time.time()
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        data=con.execute("SELECT * FROM drop_stock WHERE id=?",(drop_id,)).fetchone()
        if data is None:
            return {"ok":False,"reason":"dead"}
        if data["status"]!="live":
            return {"ok":False,"reason":"sniped" if data["remaining"]<=0 else "dead"}
        if data["ends_at"]<=now:
            con.execute("UPDATE drop_stock SET status='ended' WHERE id=?",(drop_id,))
            return {"ok":False,"reason":"dead"}
        if data["remaining"]<=0:
            con.execute("UPDATE drop_stock SET status='ended' WHERE id=?",(drop_id,))
            return {"ok":False,"reason":"sniped"}

        found=con.execute(
            "SELECT amount FROM drop_buys_v2 WHERE drop_id=? AND user_id=?",
            (drop_id,user_id)
        ).fetchone()

        current=found[0] if found else 0
        left=data["user_limit"]-current

        if left<=0:
            return {"ok":False,"reason":"limit"}

        wallet_guild=data["target_guild_id"] if data["target_guild_id"] is not None else guild_id
        if wallet_guild is None:
            return {"ok":False,"reason":"dead"}
        con.execute("INSERT OR IGNORE INTO wallets(guild_id,user_id) VALUES(?,?)",(wallet_guild,user_id))
        roses,rings=con.execute(
            "SELECT roses,rings FROM wallets WHERE guild_id=? AND user_id=?",
            (wallet_guild,user_id)
        ).fetchone()

        caps=[left,data["remaining"]]

        if data["price"]:
            caps.append(roses//data["price"])

        if data["ring_price"]:
            caps.append(rings//data["ring_price"])

        maximum=min(caps)
        qty=maximum if amount is None else amount

        if qty<1:
            return {"ok":False,"reason":"broke"}

        if qty>left:
            return {"ok":False,"reason":"limit"}

        if qty>data["remaining"]:
            return {"ok":False,"reason":"sniped"}

        rose_cost=data["price"]*qty
        ring_cost=data["ring_price"]*qty

        if roses<rose_cost or rings<ring_cost:
            return {"ok":False,"reason":"broke"}

        con.execute(
            "UPDATE wallets SET roses=roses-?,rings=rings-? WHERE guild_id=? AND user_id=?",
            (rose_cost,ring_cost,wallet_guild,user_id)
        )

        value=data["amount"]*qty
        claim=None

        if data["reward"]=="roses":
            con.execute(
                "UPDATE wallets SET roses=roses+? WHERE guild_id=? AND user_id=?",
                (value,wallet_guild,user_id)
            )

        elif data["reward"]=="rings":
            con.execute(
                "UPDATE wallets SET rings=rings+? WHERE guild_id=? AND user_id=?",
                (value,wallet_guild,user_id)
            )

        elif custom(data["reward"]):
            name=custom_name(data["reward"])
            cur=con.execute(
                "INSERT INTO claims(user,prize,time) VALUES(?,?,?)",
                (user_id,name,int(now))
            )
            claim=cur.lastrowid

        else:
            con.execute(
                """INSERT INTO items(user,item,amount)
                VALUES(?,?,?)
                ON CONFLICT(user,item)
                DO UPDATE SET amount=amount+excluded.amount""",
                (user_id,data["reward"],value)
            )

        remaining=data["remaining"]-qty

        con.execute(
            """UPDATE drop_stock
            SET remaining=?,status=?,sold_out_at=CASE WHEN ?<=0 THEN COALESCE(sold_out_at,?) ELSE sold_out_at END
            WHERE id=?""",
            (remaining,"ended" if remaining<=0 else "live",remaining,now,drop_id)
        )

        con.execute(
            """INSERT INTO drop_buys_v2(drop_id,user_id,amount)
            VALUES(?,?,?)
            ON CONFLICT(drop_id,user_id)
            DO UPDATE SET amount=amount+excluded.amount""",
            (drop_id,user_id,qty)
        )

        return {
            "ok":True,
            "reward":data["reward"],
            "value":value,
            "rose_cost":rose_cost,
            "ring_cost":ring_cost,
            "claim":claim
        }

def custom(reward):
    return reward.startswith("custom:")

def custom_name(reward):
    return reward.split(":",1)[1] if custom(reward) else None

def meta(data):
    if custom(data["reward"]):
        return "🎟️",custom_name(data["reward"])
    return REWARDS[data["reward"]]

def prize(data,value=None):
    emoji,label=meta(data)
    amount=data["amount"] if value is None else value

    if data["reward"]=="roses":
        return f"{emoji} **{amount:,} roses**"

    if data["reward"]=="rings":
        return f"{emoji} **{amount:,} {'ring' if amount==1 else 'rings'}**"

    if custom(data["reward"]):
        return f"{emoji} **{label}**"

    return f"{emoji} **{amount:,}× {label}**"

def pay(data):
    parts=[]
    if data["price"]:
        parts.append(f"{data['price']:,} roses {rosieemoji.ROSE}")
    if data["ring_price"]:
        parts.append(f"{data['ring_price']:,} {'ring' if data['ring_price']==1 else 'rings'} 💍")
    return " ⊹ ".join(parts) if parts else "free"

def panel(guild_id=None):
    current=live(guild_id)
    upcoming=scheduled(guild_id)
    parts=[]
    if current:
        parts.append(f"**live**\n{prize(current)}\nprice ⊹ **{pay(current)}**\nstock ⊹ **{current['remaining']:,} / {current['stock']:,}**\nends ⊹ <t:{int(current['ends_at'])}:R>")
    else:
        parts.append("**live**\nnone")
    if upcoming:
        lines=[]
        for data in upcoming:
            lines.append(f"{prize(data)}\nprice ⊹ **{pay(data)}** • stock ⊹ **{data['stock']:,}**\ndrops ⊹ <t:{int(data['start_at'])}:F> • <t:{int(data['start_at'])}:R>")
        parts.append("**scheduled**\n"+"\n\n".join(lines))
    else:
        parts.append("**scheduled**\nnone")
    return discord.Embed(title="🎁 drops",description="\n\n".join(parts),color=discord.Color.dark_red())

def stocked(data):
    release=f"<t:{int(data['start_at'])}:F>" if data["status"]=="scheduled" else "manual"
    return discord.Embed(title="🎁 stocked drop",description=f"{prize(data)}\n\nprice ⊹ **{pay(data)}**\nstock ⊹ **{data['stock']:,}**\nlimit ⊹ **{data['user_limit']:,} per person**\nrelease ⊹ **{release}**\nlive for ⊹ **{data['duration']:,} minutes**",color=discord.Color.dark_red())

def when(day_text,clock_text):
    now=game.now()
    raw=" ".join(clock_text.strip().upper().split())
    clock=None

    for form in ("%I:%M %p","%I %p","%H:%M"):
        try:
            clock=datetime.strptime(raw,form).time()
            break
        except ValueError:
            pass

    if clock is None:
        raise ValueError("format")

    raw=(day_text or "today").strip().lower()

    if raw in ("","today"):
        d=now.date()

    elif raw=="tomorrow":
        d=now.date()+timedelta(days=1)

    else:
        d=None

        for form in ("%Y-%m-%d","%Y/%m/%d","%m/%d/%Y","%m-%d-%Y"):
            try:
                d=datetime.strptime(raw,form).date()
                break
            except ValueError:
                pass

        if d is None:
            for form in ("%m/%d","%m-%d"):
                try:
                    x=datetime.strptime(raw,form)
                    d=date(now.year,x.month,x.day)
                    break
                except ValueError:
                    pass

        if d is None:
            raise ValueError("format")

    value=datetime(
        d.year,
        d.month,
        d.day,
        clock.hour,
        clock.minute,
        tzinfo=game.ET
    )

    if value<=now:
        raise ValueError("past")

    return value.timestamp()

async def getchannel(bot,channel_id):
    if channel_id is None:
        return None
    target=bot.get_channel(channel_id)
    if target is not None:
        return target
    try:
        return await bot.fetch_channel(channel_id)
    except discord.HTTPException:
        return None

async def alertchannel(bot,data,channel=None):
    target_id=data["target_guild_id"]
    if target_id is None:
        legacy_id=legacyconfig.DROP_CHANNEL_ID

        if not legacy_id:
            return None

        legacy=await getchannel(
            bot,
            legacy_id
        )

        if legacy is None:
            return None
        guild=getattr(legacy,"guild",None)
        settings=guildconfig.get(guild.id) if guild else None
        if settings and settings["drop_channel_id"]:
            target=await getchannel(bot,settings["drop_channel_id"])
            if target is not None and getattr(getattr(target,"guild",None),"id",None)==guild.id:
                return target
        return legacy
    settings=guildconfig.drops(target_id)
    target=await getchannel(bot,settings["drop_channel_id"])
    if target is not None and getattr(getattr(target,"guild",None),"id",None)==target_id:
        return target
    if channel is not None and getattr(getattr(channel,"guild",None),"id",None)==target_id:
        return channel
    if data["guild_id"]==target_id:
        target=await getchannel(bot,data["channel_id"])
        if target is not None and getattr(getattr(target,"guild",None),"id",None)==target_id:
            return target
    return None

async def pingdrop(bot,data,manual=False,channel=None):
    target=await alertchannel(bot,data,channel)
    if target is None:
        return False
    guild=getattr(target,"guild",None)
    role=pingrole(guild) if pingson(guild) else None
    mention=f"{role.mention} " if role else ""
    if manual:
        text=f"{mention}‼️ **drop live**\n\n{prize(data)}\nprice ⊹ **{pay(data)}**\nstock ⊹ **{data['remaining']:,} / {data['stock']:,}**\nlimit ⊹ **{data['user_limit']:,} per person**\nends ⊹ <t:{int(data['ends_at'])}:R>"
    else:
        text=f"{mention}‼️ **drop soon**\n\n{prize(data)}\nprice ⊹ **{pay(data)}**\nstock ⊹ **{data['stock']:,}**\nlimit ⊹ **{data['user_limit']:,} per person**\ndrops ⊹ <t:{int(data['start_at'])}:R>"
    try:
        await target.send(text,allowed_mentions=discord.AllowedMentions(everyone=False,users=False,roles=role is not None))
        return True
    except discord.HTTPException:
        return False


class UnlockView(discord.ui.View):
    def __init__(self,bot,user_id,guild_id,channel_id,message_id):
        super().__init__(timeout=60)
        self.bot=bot
        self.user_id=user_id
        self.guild_id=guild_id
        self.channel_id=channel_id
        self.message_id=message_id

    async def parent(self):
        try:
            channel=self.bot.get_channel(self.channel_id) or await self.bot.fetch_channel(self.channel_id)
            msg=await channel.fetch_message(self.message_id)
            await msg.edit(embed=panel(self.guild_id),view=Controls(self.bot,self.user_id,self.guild_id,live(self.guild_id)))
        except discord.HTTPException:
            pass

    @discord.ui.button(emoji="💍",style=discord.ButtonStyle.danger)
    async def yes(self,it:discord.Interaction,button:discord.ui.Button):
        if it.user.id!=self.user_id:
            await it.response.send_message("nuh uh",ephemeral=True)
            return
        if not unlock(self.guild_id,it.user.id):
            await it.response.edit_message(content="broke broski you need 1 ring 💍",embed=None,view=None)
            return
        await it.response.edit_message(content="refresh unlocked ⊹ 🔄",embed=None,view=None)
        await self.parent()

    @discord.ui.button(emoji="❌",style=discord.ButtonStyle.secondary)
    async def no(self,it:discord.Interaction,button:discord.ui.Button):
        if it.user.id!=self.user_id:
            await it.response.send_message("nuh uh",ephemeral=True)
            return
        await it.response.edit_message(content="nah",embed=None,view=None)

def rewardhandler(guild):
    if guild is None:
        return None

    return fulfillment.handler(
        guild.id,
        "reward"
    )


def rewardmention(guild):
    user_id=rewardhandler(
        guild
    )

    return (
        f"<@{user_id}> pay up ahaha"
        if user_id
        else "waiting on fulfillment"
    )


async def make_ticket(bot,guild,user):
    app=await bot.application_info()

    owner=guild.get_member(app.owner.id)

    if owner is None:
        try:
            owner=await guild.fetch_member(app.owner.id)
        except discord.HTTPException:
            owner=None

    handler_id=rewardhandler(
        guild
    )

    staff=(
        guild.get_member(
            handler_id
        )
        if handler_id
        else None
    )

    if (
        staff is None
        and handler_id
    ):
        try:
            staff=await guild.fetch_member(
                handler_id
            )
        except discord.HTTPException:
            staff=None

    category=next(
        (
            x for x in guild.categories
            if x.name.casefold()=="redemptions"
        ),
        None
    )

    try:
        if category is None:
            category=await guild.create_category(
                "Redemptions",
                reason="rosie redemptions"
            )
        elif category.name!="Redemptions":
            await category.edit(
                name="Redemptions",
                reason="rosie redemption category"
            )

        allow=discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True
        )

        overwrites={
            guild.default_role:discord.PermissionOverwrite(view_channel=False),
            guild.me:allow,
            user:allow
        }

        if owner is not None:
            overwrites[owner]=allow

        if staff is not None:
            overwrites[staff]=allow

        return await guild.create_text_channel(
            f"redeem-{user.id}",
            category=category,
            overwrites=overwrites,
            reason=f"custom drop bought by {user}"
        )

    except discord.HTTPException:
        return None

class Buy(discord.ui.Button):
    def __init__(self,maxed=False):
        super().__init__(
            label="buy max" if maxed else "buy 1",
            style=discord.ButtonStyle.secondary if maxed else discord.ButtonStyle.danger,
            row=0
        )
        self.maxed=maxed

    async def callback(self,it:discord.Interaction):
        view=self.view

        if it.user.id!=view.user_id:
            await it.response.send_message(
                "make ur own /drops",
                ephemeral=True
            )
            return

        data=get(view.drop_id)

        if data is None:
            await it.response.send_message(
                "drop is over",
                ephemeral=True
            )
            return

        ticket=None

        if custom(data["reward"]):
            await it.response.defer(ephemeral=True)

            ticket=await make_ticket(view.bot,it.guild,it.user)

            if ticket is None:
                await it.followup.send(
                    "ticket machine died 💔 try again",
                    ephemeral=True
                )
                return

        result=buy(
            view.drop_id,
            it.guild.id,
            it.user.id,
            None if self.maxed else 1
        )

        if not result["ok"]:
            if ticket is not None:
                try:
                    await ticket.delete(reason="drop purchase failed")
                except discord.HTTPException:
                    pass

            text={
                "dead":"drop is over",
                "limit":"you hit ur limit",
                "sniped":"sniped 💔",
                "broke":"broke broski"
            }[result["reason"]]

            if it.response.is_done():
                await it.followup.send(text,ephemeral=True)
            else:
                await it.response.send_message(text,ephemeral=True)

            return

        game.touch(it.user.id)

        if ticket is not None:
            claim=result["claim"]
            name=custom_name(result["reward"])

            try:
                await ticket.edit(
                    name=f"redeem-{claim}",
                    topic=f"claim:{claim} • user:{it.user.id} • prize:{name}"
                )
            except discord.HTTPException:
                pass

            receipt=await ticket.send(
                f"🎟️ **redemption #{claim}**\n"
                f"winner • {it.user.mention} (`{it.user.id}`)\n"
                f"**{name}**\n\n"
                f"{rewardmention(it.guild)}",
                view=RedeemView(view.bot)
            )

            try:
                await receipt.pin(reason="redemption receipt")
            except discord.HTTPException:
                pass

            try:
                await it.message.edit(
                    embed=panel(view.guild_id),
                    view=Controls(
                        view.bot,
                        view.user_id,
                        view.guild_id,
                        live(view.guild_id)
                    )
                )
            except discord.HTTPException:
                pass

            await it.followup.send(
                f"bought ⊹ **{name}** 🎟️\n"
                f"ticket made ⊹ {ticket.mention}",
                ephemeral=True
            )
            return

        await it.response.edit_message(
            embed=panel(view.guild_id),
            view=Controls(
                view.bot,
                view.user_id,
                view.guild_id,
                live(view.guild_id)
            )
        )

        emoji,label=REWARDS[result["reward"]]

        won=(
            f"{result['value']:,} {label} {emoji}"
            if result["reward"] in ("roses","rings")
            else f"{result['value']:,}× {label} {emoji}"
        )

        paid=[]

        if result["rose_cost"]:
            paid.append(
                f"{result['rose_cost']:,} roses {rosieemoji.ROSE}"
            )

        if result["ring_cost"]:
            paid.append(
                f"{result['ring_cost']:,} "
                f"{'ring' if result['ring_cost']==1 else 'rings'} 💍"
            )

        await it.followup.send(
            f"bought ⊹ **{won}**\n"
            f"spent ⊹ **{' ⊹ '.join(paid) if paid else 'free'}**",
            ephemeral=True
        )

class Refresh(discord.ui.Button):
    def __init__(self,ready):
        super().__init__(emoji="🔄" if ready else "💍",style=discord.ButtonStyle.secondary,row=0)

    async def callback(self,it:discord.Interaction):
        view=self.view
        if it.user.id!=view.user_id:
            await it.response.send_message("make ur own /drops",ephemeral=True)
            return
        if unlocked(it.user.id):
            await it.response.edit_message(embed=panel(view.guild_id),view=Controls(view.bot,view.user_id,view.guild_id,live(view.guild_id)))
            return
        await it.response.send_message(embed=discord.Embed(title="🎁 refresh",description="cost ⊹ **1 ring 💍**",color=discord.Color.dark_red()),view=UnlockView(view.bot,view.user_id,view.guild_id,it.channel.id,it.message.id),ephemeral=True)

class PingToggle(discord.ui.Button):
    def __init__(self,enabled):
        super().__init__(emoji="‼️",style=discord.ButtonStyle.success if enabled else discord.ButtonStyle.secondary,row=0)

    async def callback(self,it:discord.Interaction):
        view=self.view
        if it.user.id!=view.user_id:
            await it.response.send_message("make ur own /drops",ephemeral=True)
            return
        if not pingson(it.guild):
            await it.response.send_message("drop pings are off in this server",ephemeral=True)
            return
        role=pingrole(it.guild)
        if role is None:
            await it.response.send_message("this server has no drop ping role set",ephemeral=True)
            return
        try:
            if role in it.user.roles:
                await it.user.remove_roles(role,reason="Rosie drop ping toggle")
                enabled=False
                text="drop pings off ‼️"
            else:
                await it.user.add_roles(role,reason="Rosie drop ping toggle")
                enabled=True
                text="drop pings on ‼️"
        except discord.Forbidden:
            await it.response.send_message("rosie needs manage roles + her role above Drop Ping",ephemeral=True)
            return
        await it.response.edit_message(embed=panel(view.guild_id),view=Controls(view.bot,view.user_id,view.guild_id,live(view.guild_id),enabled))
        await it.followup.send(text,ephemeral=True)

class Controls(discord.ui.View):
    def __init__(self,bot,user_id,guild_id,data,ping_on=None):
        super().__init__(timeout=3600)
        self.bot=bot
        self.user_id=user_id
        self.guild_id=guild_id
        self.drop_id=data["id"] if data else None
        guild=bot.get_guild(guild_id)
        if ping_on is None:
            ping_on=hasping(guild,user_id)
        if data:
            self.add_item(Buy())
            if not custom(data["reward"]):
                self.add_item(Buy(True))
        self.add_item(Refresh(unlocked(user_id)))
        if pingson(guild) and pingrole(guild) is not None:
            self.add_item(PingToggle(ping_on))

class Drops(commands.Cog):
    def __init__(self,bot):
        self.bot=bot
        self.registry_done=False
        self.clock.start()

    async def registry(self):
        if self.registry_done:
            return

        app_id=self.bot.application_id or self.bot.user.id

        rows=await self.bot.http.get_global_commands(
            app_id
        )

        row=next(
            (
                item
                for item in rows
                if item.get("name")=="drops"
                and int(item.get("type",1))==1
            ),
            None
        )

        payload={
            "name":"drops",
            "description":"view active and scheduled drops",
            "type":1,
            "dm_permission":False,
            "options":[]
        }

        if row is None:
            route=Route(
                "POST",
                "/applications/{application_id}/commands",
                application_id=app_id
            )
        else:
            route=Route(
                "PATCH",
                "/applications/{application_id}/commands/{command_id}",
                application_id=app_id,
                command_id=row["id"]
            )

        await self.bot.http.request(
            route,
            json=payload
        )

        self.registry_done=True

        print(
            "drops command registry ✓"
        )

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            await self.registry()

        except Exception as error:
            print(
                f"drops registry failed ⊹ {error}"
            )

    def cog_unload(self):
        self.clock.cancel()

    async def fire(self,data):
        shot=armed(data["id"])
        if shot is None:
            return

        clear(data["id"])

        user_id=shot["user_id"]
        maxed=not custom(data["reward"])

        result=buy(
            data["id"],
            shot["guild_id"],
            user_id,
            None if maxed else 1
        )

        user=self.bot.get_user(user_id)

        if user is None:
            try:
                user=await self.bot.fetch_user(user_id)
            except discord.HTTPException:
                user=None

        if not result["ok"]:
            if user is not None:
                text={
                    "dead":"drop is over",
                    "limit":"you hit ur limit",
                    "sniped":"sniped 💔",
                    "broke":"broke broski"
                }[result["reason"]]

                try:
                    await user.send(
                        f"snipe missed ⊹ **{text}**"
                    )
                except discord.HTTPException:
                    pass

            return

        game.touch(user_id)

        if custom(result["reward"]):
            guild=self.bot.get_guild(
                data["target_guild_id"]
                if data["target_guild_id"] is not None
                else shot["guild_id"]
            )

            member=(
                guild.get_member(user_id)
                if guild
                else None
            )

            if guild is not None and member is None:
                try:
                    member=await guild.fetch_member(
                        user_id
                    )
                except discord.HTTPException:
                    member=None

            made=None

            if guild is not None and member is not None:
                made=await make_ticket(
                    self.bot,
                    guild,
                    member
                )

            if made is not None:
                claim=result["claim"]
                name=custom_name(
                    result["reward"]
                )

                try:
                    await made.edit(
                        name=f"redeem-{claim}",
                        topic=(
                            f"claim:{claim} • "
                            f"user:{user_id} • "
                            f"prize:{name}"
                        )
                    )
                except discord.HTTPException:
                    pass

                try:
                    receipt=await made.send(
                        f"🎟️ **redemption #{claim}**\n"
                        f"winner • <@{user_id}> (`{user_id}`)\n"
                        f"**{name}**\n\n"
                        f"{rewardmention(guild)}",
                        view=RedeemView(self.bot)
                    )

                    try:
                        await receipt.pin(
                            reason="redemption receipt"
                        )
                    except discord.HTTPException:
                        pass

                except discord.HTTPException:
                    pass

            if user is not None:
                name=custom_name(
                    result["reward"]
                )

                text=(
                    f"snipe hit ⊹ **{name}** 🎟️"
                )

                if made is not None:
                    text+=(
                        f"\nticket made ⊹ "
                        f"{made.mention}"
                    )
                else:
                    text+=(
                        "\nticket machine died 💔 "
                        "tell staff"
                    )

                try:
                    await user.send(text)
                except discord.HTTPException:
                    pass

            return

        emoji,label=REWARDS[
            result["reward"]
        ]

        won=(
            f"{result['value']:,} "
            f"{label} {emoji}"
            if result["reward"] in (
                "roses",
                "rings"
            )
            else
            f"{result['value']:,}× "
            f"{label} {emoji}"
        )

        paid=[]

        if result["rose_cost"]:
            paid.append(
                f"{result['rose_cost']:,} roses {rosieemoji.ROSE}"
            )

        if result["ring_cost"]:
            paid.append(
                f"{result['ring_cost']:,} "
                f"{'ring' if result['ring_cost']==1 else 'rings'} 💍"
            )

        if user is not None:
            try:
                await user.send(
                    f"snipe hit ⊹ **{won}**\n"
                    f"spent ⊹ **"
                    f"{' ⊹ '.join(paid) if paid else 'free'}"
                    f"**"
                )
            except discord.HTTPException:
                pass

    @tasks.loop(seconds=1)
    async def clock(self):
        for data in lives():
            if data["ends_at"]<=time.time() or data["remaining"]<=0:
                stop(data["id"])
        for data in warnings():
            if await pingdrop(self.bot,data):
                mark_ping(data["id"])
        for data in due():
            started=start(
                data["id"],
                data["channel_id"]
            )

            if started:
                await self.fire(started)

    @clock.before_loop
    async def ready(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="drops",description="view active and scheduled drops")
    @app_commands.guild_only()
    async def drops(self,it:discord.Interaction):
        game.touch(it.user.id)
        data=live(it.guild.id)

        await it.response.send_message(
            embed=panel(it.guild.id),
            view=Controls(
                self.bot,
                it.user.id,
                it.guild.id,
                data
            )
        )

async def setup(bot):
    init()
    guildconfig.init()
    await bot.add_cog(Drops(bot))
