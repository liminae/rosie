import sqlite3
import time

import discord
from core import database
from core import game
from discord import app_commands
from discord.ext import commands
from core import emoji as rosieemoji

COLS={"roses":"roses","rings":"rings"}
EMOJI={"roses":rosieemoji.ROSE,"rings":"💍"}

def connect():
    con=sqlite3.connect(database.FILE,timeout=10)
    con.row_factory=sqlite3.Row
    return con

def init():
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS transfers(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            currency TEXT NOT NULL,
            amount INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            created_at REAL NOT NULL
        )""")

def move(sender,receiver,currency,amount,guild_id,channel_id):
    col=COLS[currency]
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        con.execute("INSERT OR IGNORE INTO wallets(guild_id,user_id) VALUES(?,?)",(guild_id,sender))
        con.execute("INSERT OR IGNORE INTO wallets(guild_id,user_id) VALUES(?,?)",(guild_id,receiver))
        row=con.execute(f"SELECT {col} FROM wallets WHERE guild_id=? AND user_id=?",(guild_id,sender)).fetchone()
        balance=int(row[col])
        if balance<amount:
            return {"ok":False,"balance":balance}
        cur=con.execute(f"UPDATE wallets SET {col}={col}-? WHERE guild_id=? AND user_id=? AND {col}>=?",(amount,guild_id,sender,amount))
        if cur.rowcount!=1:
            return {"ok":False,"balance":balance}
        con.execute(f"UPDATE wallets SET {col}={col}+? WHERE guild_id=? AND user_id=?",(amount,guild_id,receiver))
        con.execute("INSERT INTO transfers(sender_id,receiver_id,currency,amount,guild_id,channel_id,created_at) VALUES(?,?,?,?,?,?,?)",(sender,receiver,currency,amount,guild_id,channel_id,time.time()))
    return {"ok":True}

class Transfer(commands.Cog):
    @app_commands.command(name="transfer",description="transfer roses or rings")
    @app_commands.guild_only()
    @app_commands.choices(currency=[
        app_commands.Choice(name="roses",value="roses"),
        app_commands.Choice(name="rings",value="rings")
    ])
    async def transfer(self,it:discord.Interaction,user:discord.Member,currency:app_commands.Choice[str],amount:int):
        if amount<1:
            await it.response.send_message("gimme a real number",ephemeral=True)
            return
        if user.id==it.user.id:
            await it.response.send_message("girl thats you",ephemeral=True)
            return
        if user.bot:
            await it.response.send_message("not to bots babe",ephemeral=True)
            return
        try:
            result=move(it.user.id,user.id,currency.value,amount,it.guild.id,it.channel.id)
        except (sqlite3.Error,OverflowError):
            await it.response.send_message("transfer machine died 💔 try again",ephemeral=True)
            return
        if not result["ok"]:
            short=max(0,amount-result["balance"])
            await it.response.send_message(f"broke broski you need {short:,} more {EMOJI[currency.value]}",ephemeral=True)
            return
        game.touch(it.user.id)
        game.touch(user.id)
        word=currency.value[:-1] if amount==1 else currency.value
        await it.response.send_message(f"**{amount:,} {word} {EMOJI[currency.value]}**\n**{it.user.mention}** ⊹ **{user.mention}**")

async def setup(bot):
    init()
    await bot.add_cog(Transfer())
