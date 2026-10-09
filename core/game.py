import hashlib
import json
import secrets
import sqlite3
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from core import emoji as rosieemoji

DB=Path(__file__).resolve().parents[1]/"rosie_games.db"
ET=ZoneInfo("America/New_York")
MILESTONES={
    7:(500,0),
    30:(2500,0),
    100:(0,1),
    365:(0,3)
}
CARDS=[
    [(rosieemoji.ROSE,"roses",100,'100 roses ' + rosieemoji.ROSE),("♥️","roses",400,'400 roses ' + rosieemoji.ROSE),("🎀","roses",1000,'1,000 roses ' + rosieemoji.ROSE)],
    [(rosieemoji.ROSE,"roses",200,'200 roses ' + rosieemoji.ROSE),("♥️","roses",500,'500 roses ' + rosieemoji.ROSE),("🎀","roses",800,'800 roses ' + rosieemoji.ROSE)],
    [(rosieemoji.ROSE,"roses",250,'250 roses ' + rosieemoji.ROSE),("♥️","roses",500,'500 roses ' + rosieemoji.ROSE),("🎀","roses",750,'750 roses ' + rosieemoji.ROSE)],
    [(rosieemoji.ROSE,"roses",300,'300 roses ' + rosieemoji.ROSE),("♥️","roses",500,'500 roses ' + rosieemoji.ROSE),("🎀","roses",700,'700 roses ' + rosieemoji.ROSE)],
    [(rosieemoji.ROSE,"roses",350,'350 roses ' + rosieemoji.ROSE),("♥️","roses",500,'500 roses ' + rosieemoji.ROSE),("🎀","roses",650,'650 roses ' + rosieemoji.ROSE)],
    [(rosieemoji.ROSE,"roses",100,'100 roses ' + rosieemoji.ROSE),("♥️","roses",600,'600 roses ' + rosieemoji.ROSE),("🎀","roses",800,'800 roses ' + rosieemoji.ROSE)],
    [(rosieemoji.ROSE,"roses",150,'150 roses ' + rosieemoji.ROSE),("♥️","roses",550,'550 roses ' + rosieemoji.ROSE),("🎀","roses",800,'800 roses ' + rosieemoji.ROSE)],
    [(rosieemoji.ROSE,"roses",200,'200 roses ' + rosieemoji.ROSE),("♥️","roses",400,'400 roses ' + rosieemoji.ROSE),("🎀","roses",900,'900 roses ' + rosieemoji.ROSE)],
    [(rosieemoji.ROSE,"roses",250,'250 roses ' + rosieemoji.ROSE),("♥️","roses",350,'350 roses ' + rosieemoji.ROSE),("🎀","roses",900,'900 roses ' + rosieemoji.ROSE)],
    [(rosieemoji.ROSE,"roses",300,'300 roses ' + rosieemoji.ROSE),("♥️","roses",300,'300 roses ' + rosieemoji.ROSE),("🎀","roses",900,'900 roses ' + rosieemoji.ROSE)]
]
FIELDS={"boxes_opened","rings_redeemed","robux_redeemed","scratch_plays","scratch_wins","scratch_jackpots"}

def connect():
    con=sqlite3.connect(DB)
    con.row_factory=sqlite3.Row
    return con

def init():
    with connect() as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("""CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            daily_last TEXT,
            daily_streak INTEGER NOT NULL DEFAULT 0,
            daily_best INTEGER NOT NULL DEFAULT 0,
            daily_claims INTEGER NOT NULL DEFAULT 0,
            scratch_plays INTEGER NOT NULL DEFAULT 0,
            scratch_wins INTEGER NOT NULL DEFAULT 0,
            scratch_jackpots INTEGER NOT NULL DEFAULT 0,
            boxes_opened INTEGER NOT NULL DEFAULT 0,
            rings_redeemed INTEGER NOT NULL DEFAULT 0,
            robux_redeemed INTEGER NOT NULL DEFAULT 0
        )""")
        cols={row[1] for row in con.execute("PRAGMA table_info(users)")}
        if "scratch_jackpots" not in cols:
            con.execute("ALTER TABLE users ADD COLUMN scratch_jackpots INTEGER NOT NULL DEFAULT 0")
        con.execute("""CREATE TABLE IF NOT EXISTS scratches(
            user_id INTEGER NOT NULL,
            day TEXT NOT NULL,
            card INTEGER NOT NULL,
            board TEXT NOT NULL,
            revealed TEXT NOT NULL,
            finished INTEGER NOT NULL DEFAULT 0,
            won INTEGER,
            PRIMARY KEY(user_id,day)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS redemptions(
            claim INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            robux INTEGER NOT NULL,
            closed INTEGER NOT NULL DEFAULT 0
        )""")

def now():
    return datetime.now(ET)

def day():
    return now().date()

def next_reset():
    tomorrow=day()+timedelta(days=1)
    return datetime(tomorrow.year,tomorrow.month,tomorrow.day,tzinfo=ET)

def card_index(date=None):
    date=date or day()
    digest=hashlib.sha256(("rosie:"+date.isoformat()).encode()).digest()
    return int.from_bytes(digest[:8],"big")%len(CARDS)

def card(date=None):
    return CARDS[card_index(date)]

def touch(user_id):
    with connect() as con:
        con.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)",(user_id,))

def bump(user_id,field,amount=1):
    if field not in FIELDS:
        raise ValueError("invalid stat")
    with connect() as con:
        con.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)",(user_id,))
        con.execute(f"UPDATE users SET {field}={field}+? WHERE user_id=?",(amount,user_id))

def claim_daily(user_id):
    today=day()
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        con.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)",(user_id,))
        row=con.execute("SELECT daily_last,daily_streak,daily_best FROM users WHERE user_id=?",(user_id,)).fetchone()
        last=datetime.fromisoformat(row["daily_last"]).date() if row["daily_last"] else None
        if last==today:
            return {"claimed":False,"streak":row["daily_streak"],"best":row["daily_best"],"bonus_roses":0,"bonus_rings":0}
        streak=row["daily_streak"]+1 if last==today-timedelta(days=1) else 1
        best=max(row["daily_best"],streak)
        bonus_roses,bonus_rings=MILESTONES.get(streak,(0,0))
        con.execute("UPDATE users SET daily_last=?,daily_streak=?,daily_best=?,daily_claims=daily_claims+1 WHERE user_id=?",(today.isoformat(),streak,best,user_id))
        return {"claimed":True,"streak":streak,"best":best,"bonus_roses":bonus_roses,"bonus_rings":bonus_rings}

def has_daily(user_id):
    with connect() as con:
        row=con.execute("SELECT daily_last FROM users WHERE user_id=?",(user_id,)).fetchone()
    return bool(row and row["daily_last"]==day().isoformat())

def current_streak(user_id):
    with connect() as con:
        row=con.execute("SELECT daily_last,daily_streak FROM users WHERE user_id=?",(user_id,)).fetchone()
    if not row or not row["daily_last"]:
        return 0
    last=datetime.fromisoformat(row["daily_last"]).date()
    return row["daily_streak"] if last>=day()-timedelta(days=1) else 0

def stats(user_id):
    touch(user_id)
    with connect() as con:
        row=con.execute("SELECT * FROM users WHERE user_id=?",(user_id,)).fetchone()
    data=dict(row)
    data["daily_streak"]=current_streak(user_id)
    return data

def all_stats():
    with connect() as con:
        rows=con.execute("SELECT * FROM users").fetchall()
    today=day()
    data={}
    for row in rows:
        item=dict(row)
        if item["daily_last"]:
            last=datetime.fromisoformat(item["daily_last"]).date()
            if last<today-timedelta(days=1):
                item["daily_streak"]=0
        data[item["user_id"]]=item
    return data

def user_ids():
    return list(all_stats())

def decode(row):
    data=dict(row)
    data["board"]=json.loads(data["board"])
    data["revealed"]=json.loads(data["revealed"])
    data["finished"]=bool(data["finished"])
    return data

def scratch_state(user_id):
    today=day().isoformat()
    with connect() as con:
        row=con.execute("SELECT * FROM scratches WHERE user_id=? AND day=?",(user_id,today)).fetchone()
    return decode(row) if row else None

def reset_scratch(user_id):
    with connect() as con:
        con.execute("DELETE FROM scratches WHERE user_id=? AND day=?",(user_id,day().isoformat()))

def start_scratch(user_id,force_jackpot=False):
    touch(user_id)
    today=day().isoformat()
    state=scratch_state(user_id)
    old=state is not None and len(state["board"])!=12
    if state is not None and not old:
        return state
    board=[0,1,2]+[-1]*9
    if not force_jackpot:
        secrets.SystemRandom().shuffle(board)
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        if old:
            con.execute("DELETE FROM scratches WHERE user_id=? AND day=?",(user_id,today))
        exists=con.execute("SELECT 1 FROM scratches WHERE user_id=? AND day=?",(user_id,today)).fetchone()
        if exists is None:
            con.execute("DELETE FROM scratches WHERE user_id=? AND day<>?",(user_id,today))
            con.execute("INSERT INTO scratches(user_id,day,card,board,revealed,won) VALUES(?,?,?,?,?,0)",(user_id,today,card_index(),json.dumps(board),"[]"))
            if not old:
                con.execute("UPDATE users SET scratch_plays=scratch_plays+1 WHERE user_id=?",(user_id,))
    return scratch_state(user_id)

def reveal_scratch(user_id,index):
    today=day().isoformat()
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        row=con.execute("SELECT * FROM scratches WHERE user_id=? AND day=?",(user_id,today)).fetchone()
        if row is None:
            return None,None
        state=decode(row)
        if state["finished"] or index in state["revealed"] or index<0 or index>=len(state["board"]):
            return state,None
        state["revealed"].append(index)
        prize=state["board"][index] if state["board"][index]>=0 else None
        state["finished"]=len(state["revealed"])>=4
        found={state["board"][i] for i in state["revealed"] if state["board"][i]>=0}
        jackpot=len(found)==3
        new_jackpot=jackpot and not bool(row["won"])
        con.execute("UPDATE scratches SET revealed=?,finished=?,won=? WHERE user_id=? AND day=?",(json.dumps(state["revealed"]),int(state["finished"]),int(jackpot or bool(row["won"])),user_id,today))
        if new_jackpot:
            con.execute("UPDATE users SET scratch_jackpots=scratch_jackpots+1 WHERE user_id=?",(user_id,))
        state["won"]=int(jackpot or bool(row["won"]))
        return state,prize

def register_redemption(claim,user_id,robux):
    with connect() as con:
        con.execute("INSERT OR IGNORE INTO redemptions(claim,user_id,robux) VALUES(?,?,?)",(claim,user_id,robux))

def close_redemption(claim):
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        row=con.execute("SELECT user_id,robux,closed FROM redemptions WHERE claim=?",(claim,)).fetchone()
        if row is None or row["closed"]:
            return False
        con.execute("UPDATE redemptions SET closed=1 WHERE claim=?",(claim,))
        con.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)",(row["user_id"],))
        con.execute("UPDATE users SET robux_redeemed=robux_redeemed+? WHERE user_id=?",(row["robux"],row["user_id"]))
        return True

init()
