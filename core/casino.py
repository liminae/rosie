import sqlite3

from core import database
from core import game
from core import emoji as rosieemoji

DB=game.DB
CAP=10000

def connect(econ=False):
    con=sqlite3.connect(DB,timeout=10)
    con.row_factory=sqlite3.Row
    if econ:
        con.execute("ATTACH DATABASE ? AS econ",(str(database.FILE),))
    return con

def init():
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS casino_days(
            user_id INTEGER NOT NULL,
            day TEXT NOT NULL,
            wagered INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id,day)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS blackjack_games(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            user_id INTEGER NOT NULL,
            bet INTEGER NOT NULL,
            player TEXT NOT NULL,
            dealer TEXT NOT NULL,
            deck TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            payout INTEGER NOT NULL DEFAULT 0,
            doubled INTEGER NOT NULL DEFAULT 0,
            started_at REAL NOT NULL,
            ended_at REAL
        )""")
        cols={row[1] for row in con.execute("PRAGMA table_info(blackjack_games)")}
        if "guild_id" not in cols:
            con.execute("ALTER TABLE blackjack_games ADD COLUMN guild_id INTEGER")
        con.execute("DROP INDEX IF EXISTS blackjack_one_active")
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS blackjack_one_active ON blackjack_games(guild_id,user_id) WHERE status='active'")

def migrateguild(guild_id):
    with connect() as con:
        con.execute("UPDATE blackjack_games SET guild_id=? WHERE guild_id IS NULL",(guild_id,))

def touch_con(con,guild_id,user_id):
    today=game.day().isoformat()
    con.execute("INSERT OR IGNORE INTO casino_days(user_id,day) VALUES(?,?)",(user_id,today))
    con.execute("INSERT OR IGNORE INTO econ.wallets(guild_id,user_id) VALUES(?,?)",(guild_id,user_id))
    return today

def reserve_con(con,guild_id,user_id,amount,low,high):
    today=touch_con(con,guild_id,user_id)
    balance=con.execute("SELECT roses FROM econ.wallets WHERE guild_id=? AND user_id=?",(guild_id,user_id)).fetchone()["roses"]
    wagered=con.execute("SELECT wagered FROM casino_days WHERE user_id=? AND day=?",(user_id,today)).fetchone()["wagered"]
    remaining=max(0,CAP-wagered)

    if amount<low:
        return {"ok":False,"reason":"min","min":low}
    if amount>high:
        return {"ok":False,"reason":"fixed","max":high}

    wallet=balance//10
    allowed=min(high,wallet,remaining)

    if allowed<low:
        if remaining<low:
            return {"ok":False,"reason":"cap"}
        return {"ok":False,"reason":"bankroll","need":max(0,low*10-balance)}

    if amount>allowed:
        return {"ok":False,"reason":"max","max":allowed}

    cur=con.execute("UPDATE econ.wallets SET roses=roses-? WHERE guild_id=? AND user_id=? AND roses>=?",(amount,guild_id,user_id,amount))
    if cur.rowcount!=1:
        return {"ok":False,"reason":"broke"}

    con.execute("UPDATE casino_days SET wagered=wagered+? WHERE user_id=? AND day=?",(amount,user_id,today))
    return {"ok":True,"balance":balance-amount}

def extra_con(con,guild_id,user_id,amount):
    today=touch_con(con,guild_id,user_id)
    balance=con.execute("SELECT roses FROM econ.wallets WHERE guild_id=? AND user_id=?",(guild_id,user_id)).fetchone()["roses"]
    wagered=con.execute("SELECT wagered FROM casino_days WHERE user_id=? AND day=?",(user_id,today)).fetchone()["wagered"]

    if wagered+amount>CAP:
        return {"ok":False,"reason":"cap"}
    if balance<amount:
        return {"ok":False,"reason":"broke"}

    con.execute("UPDATE econ.wallets SET roses=roses-? WHERE guild_id=? AND user_id=?",(amount,guild_id,user_id))
    con.execute("UPDATE casino_days SET wagered=wagered+? WHERE user_id=? AND day=?",(amount,user_id,today))
    return {"ok":True}

def credit_con(con,guild_id,user_id,amount):
    if amount<1:
        return
    con.execute("INSERT OR IGNORE INTO econ.wallets(guild_id,user_id) VALUES(?,?)",(guild_id,user_id))
    con.execute("UPDATE econ.wallets SET roses=roses+? WHERE guild_id=? AND user_id=?",(amount,guild_id,user_id))

def play(guild_id,user_id,bet,low,high,payout):
    with connect(True) as con:
        con.execute("BEGIN IMMEDIATE")
        result=reserve_con(con,guild_id,user_id,bet,low,high)
        if not result["ok"]:
            return result
        credit_con(con,guild_id,user_id,payout)
        balance=con.execute("SELECT roses FROM econ.wallets WHERE guild_id=? AND user_id=?",(guild_id,user_id)).fetchone()["roses"]
        return {"ok":True,"payout":payout,"balance":balance}

def error(result):
    reason=result["reason"]
    if reason=="min":
        return f"minimum bet ⊹ {result['min']:,} {rosieemoji.ROSE}"
    if reason=="fixed":
        return f"maximum bet ⊹ {result['max']:,} {rosieemoji.ROSE}"
    if reason=="bankroll":
        return f"need {result['need']:,} more {rosieemoji.ROSE} before rosie lets u do that"
    if reason=="max":
        return f"max bet rn ⊹ {result['max']:,} {rosieemoji.ROSE}"
    if reason=="cap":
        return "casino's closed for u today"
    return "broke broski"

init()
