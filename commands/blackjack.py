import json
import secrets
import time

import discord
from core import casino as casino
from core import game
from discord import app_commands
from discord.ext import commands
from core import emoji as rosieemoji

RANKS=("2","3","4","5","6","7","8","9","10","J","Q","K","A")
SUITS=("♠","♥","♦","♣")
VALUES={"2":2,"3":3,"4":4,"5":5,"6":6,"7":7,"8":8,"9":9,"10":10,"J":10,"Q":10,"K":10,"A":11}

def fresh():
    deck=[f"{rank}{suit}" for _ in range(6) for suit in SUITS for rank in RANKS]
    secrets.SystemRandom().shuffle(deck)
    return deck

def value(card):
    return VALUES[card[:-1]]

def score(cards):
    total=sum(value(card) for card in cards)
    aces=sum(card.startswith("A") for card in cards)
    while total>21 and aces:
        total-=10
        aces-=1
    return total,aces>0

def natural(cards):
    return len(cards)==2 and score(cards)[0]==21

def decode(row):
    if row is None:
        return None
    data=dict(row)
    data["player"]=json.loads(data["player"])
    data["dealer"]=json.loads(data["dealer"])
    data["deck"]=json.loads(data["deck"])
    return data

def active(guild_id,user_id):
    with casino.connect() as con:
        row=con.execute(
            "SELECT * FROM blackjack_games WHERE guild_id=? AND user_id=? AND status='active' ORDER BY id DESC LIMIT 1",
            (guild_id,user_id)
        ).fetchone()
    return decode(row)

def get(game_id):
    with casino.connect() as con:
        row=con.execute("SELECT * FROM blackjack_games WHERE id=?",(game_id,)).fetchone()
    return decode(row)

def save(con,data,status=None,payout=None):
    status=status or data["status"]
    payout=data["payout"] if payout is None else payout
    ended=time.time() if status!="active" else None

    con.execute("""UPDATE blackjack_games
        SET bet=?,player=?,dealer=?,deck=?,status=?,payout=?,doubled=?,ended_at=?
        WHERE id=?""",(
        data["bet"],
        json.dumps(data["player"]),
        json.dumps(data["dealer"]),
        json.dumps(data["deck"]),
        status,
        payout,
        data["doubled"],
        ended,
        data["id"]
    ))

    data["status"]=status
    data["payout"]=payout
    data["ended_at"]=ended
    return data

def dealerplay(data):
    while True:
        total,soft=score(data["dealer"])
        if total<17 or (total==17 and soft):
            data["dealer"].append(data["deck"].pop())
        else:
            break

def settle(con,data):
    dealerplay(data)
    player=score(data["player"])[0]
    dealer=score(data["dealer"])[0]

    if player>21:
        return save(con,data,"bust",0)

    if dealer>21 or player>dealer:
        payout=data["bet"]*2
        casino.credit_con(con,data["guild_id"],data["user_id"],payout)
        return save(con,data,"won",payout)

    if player==dealer:
        payout=data["bet"]
        casino.credit_con(con,data["guild_id"],data["user_id"],payout)
        return save(con,data,"push",payout)

    return save(con,data,"lost",0)

def start(guild_id,user_id,bet):
    with casino.connect(True) as con:
        con.execute("BEGIN IMMEDIATE")

        old=con.execute(
            "SELECT * FROM blackjack_games WHERE guild_id=? AND user_id=? AND status='active' ORDER BY id DESC LIMIT 1",
            (guild_id,user_id)
        ).fetchone()
        if old:
            return {"ok":False,"reason":"active","game":decode(old)}

        reserve=casino.reserve_con(con,guild_id,user_id,bet,100,1000)
        if not reserve["ok"]:
            return reserve

        deck=fresh()
        player=[deck.pop()]
        dealer=[deck.pop()]
        player.append(deck.pop())
        dealer.append(deck.pop())

        cur=con.execute("""INSERT INTO blackjack_games(
            guild_id,user_id,bet,player,dealer,deck,status,payout,doubled,started_at
        ) VALUES(?,?,?,?,?,?,'active',0,0,?)""",(
            guild_id,
            user_id,
            bet,
            json.dumps(player),
            json.dumps(dealer),
            json.dumps(deck),
            time.time()
        ))

        data=decode(con.execute(
            "SELECT * FROM blackjack_games WHERE id=?",
            (cur.lastrowid,)
        ).fetchone())

        pb=natural(player)
        db=natural(dealer)

        if pb and db:
            casino.credit_con(con,guild_id,user_id,bet)
            data=save(con,data,"push",bet)
        elif pb:
            payout=bet*5//2
            casino.credit_con(con,guild_id,user_id,payout)
            data=save(con,data,"blackjack",payout)
        elif db:
            data=save(con,data,"dealer_blackjack",0)

        return {"ok":True,"game":data}

def action(game_id,guild_id,user_id,kind):
    with casino.connect(True) as con:
        con.execute("BEGIN IMMEDIATE")

        row=con.execute(
            "SELECT * FROM blackjack_games WHERE id=? AND guild_id=? AND status='active'",
            (game_id,guild_id)
        ).fetchone()
        if row is None:
            return {"ok":False,"reason":"dead"}

        data=decode(row)
        if data["user_id"]!=user_id:
            return {"ok":False,"reason":"owner"}

        if kind=="hit":
            data["player"].append(data["deck"].pop())
            total=score(data["player"])[0]

            if total>21:
                data=save(con,data,"bust",0)
            elif total==21:
                data=settle(con,data)
            else:
                data=save(con,data)

            return {"ok":True,"game":data}

        if kind=="stand":
            return {"ok":True,"game":settle(con,data)}

        if kind=="double":
            if len(data["player"])!=2 or data["doubled"]:
                return {"ok":False,"reason":"double"}

            extra=casino.extra_con(con,guild_id,user_id,data["bet"])
            if not extra["ok"]:
                return {"ok":False,"reason":"double_"+extra["reason"]}

            data["bet"]*=2
            data["doubled"]=1
            data["player"].append(data["deck"].pop())

            if score(data["player"])[0]>21:
                data=save(con,data,"bust",0)
            else:
                data=settle(con,data)

            return {"ok":True,"game":data}

        return {"ok":False,"reason":"action"}

def resultline(data):
    status=data["status"]
    net=data["payout"]-data["bet"]

    if status=="active":
        return ""
    if status=="blackjack":
        return f'\n\n**blackjack** ⊹ +{net:,} roses {rosieemoji.ROSE}'
    if status=="won":
        return f'\n\n**won** ⊹ +{net:,} roses {rosieemoji.ROSE}'
    if status=="push":
        return "\n\n**push**"
    if status=="bust":
        return "\n\n**bust**"
    if status=="dealer_blackjack":
        return "\n\n**dealer blackjack**"
    return "\n\n**dealer wins**"

def embed(data):
    ptotal,_=score(data["player"])
    cards=" ".join(data["player"])

    if data["status"]=="active":
        dealer=f"{data['dealer'][0]} ??"
        dscore="?"
    else:
        dealer=" ".join(data["dealer"])
        dscore=str(score(data["dealer"])[0])

    text=(
        f"bet ⊹ **{data['bet']:,} roses {rosieemoji.ROSE}**\n\n**you**\n{cards} ⊹ **{ptotal}**\n\n**dealer**\n{dealer} ⊹ **{dscore}**{resultline(data)}"
    )

    return discord.Embed(
        title="🃏 blackjack",
        description=text,
        color=discord.Color.dark_red()
    )

def error(result):
    reason=result["reason"]

    if reason in ("min","fixed","bankroll","max","cap","broke"):
        return casino.error(result)
    if reason=="active":
        return "finish ur hand first"
    if reason=="double_cap":
        return "cant double that rn"
    if reason=="double_broke":
        return "not enough roses to double"
    if reason=="double":
        return "too late to double"
    if reason=="owner":
        return "not ur blackjack"
    return "that hand is over"

class BlackjackView(discord.ui.View):
    def __init__(self,guild_id,user_id,game_id):
        super().__init__(timeout=600)
        self.guild_id=guild_id
        self.user_id=user_id
        self.game_id=game_id
        data=get(game_id)
        if data:
            self.double.disabled=len(data["player"])!=2 or bool(data["doubled"])

    async def act(self,it,kind):
        if it.user.id!=self.user_id:
            await it.response.send_message("make ur own /blackjack",ephemeral=True)
            return

        result=action(self.game_id,self.guild_id,it.user.id,kind)
        if not result["ok"]:
            await it.response.send_message(error(result),ephemeral=True)
            return

        data=result["game"]
        view=BlackjackView(self.guild_id,self.user_id,self.game_id) if data["status"]=="active" else None
        await it.response.edit_message(embed=embed(data),view=view)

    @discord.ui.button(label="hit",style=discord.ButtonStyle.danger)
    async def hit(self,it:discord.Interaction,button:discord.ui.Button):
        await self.act(it,"hit")

    @discord.ui.button(label="stand",style=discord.ButtonStyle.secondary)
    async def stand(self,it:discord.Interaction,button:discord.ui.Button):
        await self.act(it,"stand")

    @discord.ui.button(label="double",style=discord.ButtonStyle.success)
    async def double(self,it:discord.Interaction,button:discord.ui.Button):
        await self.act(it,"double")

class Blackjack(commands.Cog):
    @app_commands.command(name="blackjack",description="play blackjack")
    @app_commands.guild_only()
    @app_commands.describe(bet='bet')
    async def blackjack(self,it:discord.Interaction,bet:int=0):
        game.touch(it.user.id)

        old=active(it.guild.id,it.user.id)
        if old:
            await it.response.send_message(
                embed=embed(old),
                view=BlackjackView(it.guild.id,it.user.id,old["id"])
            )
            return

        if bet==0:
            await it.response.send_message('bet 100 - 1,000 roses ' + rosieemoji.ROSE,ephemeral=True)
            return

        result=start(it.guild.id,it.user.id,bet)
        if not result["ok"]:
            await it.response.send_message(error(result),ephemeral=True)
            return

        data=result["game"]
        view=BlackjackView(it.guild.id,it.user.id,data["id"]) if data["status"]=="active" else None
        await it.response.send_message(embed=embed(data),view=view)

async def setup(bot):
    await bot.add_cog(Blackjack())
