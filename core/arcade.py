import json
import sqlite3
import time

from core import database

GAMES=("rps","petfight")
MOVES={"rps":("rock","paper","scissors"),"petfight":("strike","guard","trick")}
TTL=1200


def connect():
    con=sqlite3.connect(database.FILE,timeout=15)
    con.row_factory=sqlite3.Row
    return con


def init():
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS arcade_matches(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            message_id INTEGER,
            challenger INTEGER NOT NULL,
            opponent INTEGER NOT NULL,
            game TEXT NOT NULL,
            status TEXT NOT NULL,
            stage TEXT NOT NULL,
            score_a INTEGER NOT NULL DEFAULT 0,
            score_b INTEGER NOT NULL DEFAULT 0,
            round INTEGER NOT NULL DEFAULT 1,
            winner INTEGER,
            data TEXT NOT NULL,
            created REAL NOT NULL,
            updated REAL NOT NULL,
            expires REAL NOT NULL
        )""")
        con.execute("CREATE INDEX IF NOT EXISTS arcade_active ON arcade_matches(guild_id,status,expires)")


def record(row):
    if row is None:
        return None
    data=dict(row)
    data["data"]=json.loads(data["data"])
    return data


def get(match_id):
    with connect() as con:
        return record(con.execute("SELECT * FROM arcade_matches WHERE id=?",(match_id,)).fetchone())


def _expire(con,now):
    con.execute("""UPDATE arcade_matches SET status='expired',updated=?
        WHERE status IN ('pending','playing') AND expires<=?""",(now,now))


def create(guild_id,channel_id,challenger,opponent,game):
    if game not in GAMES or challenger==opponent:
        return "invalid",None
    now=time.time()
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        _expire(con,now)
        occupied=con.execute("""SELECT 1 FROM arcade_matches
            WHERE guild_id=? AND status IN ('pending','playing')
            AND (challenger IN (?,?) OR opponent IN (?,?)) LIMIT 1""",
            (guild_id,challenger,opponent,challenger,opponent)).fetchone()
        if occupied:
            return "busy",None
        data={"choices":{},"pets":{},"hp":{"a":14,"b":14},
              "stamina":{"a":3,"b":3},"last":""}
        con.execute("""INSERT INTO arcade_matches(
            guild_id,channel_id,challenger,opponent,game,status,stage,data,created,updated,expires
            ) VALUES(?,?,?,?,?,'pending','invite',?,?,?,?)""",
            (guild_id,channel_id,challenger,opponent,game,json.dumps(data),now,now,now+300))
        match_id=con.execute("SELECT last_insert_rowid()").fetchone()[0]
    return "ok",get(match_id)


def bind(match_id,message_id):
    with connect() as con:
        return con.execute("UPDATE arcade_matches SET message_id=? WHERE id=? AND message_id IS NULL",
                           (message_id,match_id)).rowcount==1


def matches_to_restore():
    now=time.time()
    with connect() as con:
        _expire(con,now)
        return [record(r) for r in con.execute("""SELECT * FROM arcade_matches
            WHERE message_id IS NOT NULL AND ((status IN ('pending','playing'))
            OR (status='finished' AND updated>?)) ORDER BY id DESC LIMIT 500""",(now-86400,))]


def _save(con,m):
    con.execute("""UPDATE arcade_matches SET status=?,stage=?,score_a=?,score_b=?,round=?,
        winner=?,data=?,updated=?,expires=? WHERE id=?""",
        (m["status"],m["stage"],m["score_a"],m["score_b"],m["round"],
         m["winner"],json.dumps(m["data"]),m["updated"],m["expires"],m["id"]))


def _operate(match_id,user_id,fn):
    now=time.time()
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        _expire(con,now)
        m=record(con.execute("SELECT * FROM arcade_matches WHERE id=?",(match_id,)).fetchone())
        if not m:
            return "missing",None
        if user_id not in (m["challenger"],m["opponent"]):
            return "forbidden",m
        status=fn(m,user_id)
        if status in ("ok","round","finished","waiting","picked"):
            m["updated"]=now
            m["expires"]=now+TTL if m["status"]=="playing" else now+300
            _save(con,m)
        return status,m


def decision(match_id,user_id,choice):
    def apply(m,u):
        if m["status"]!="pending":
            return "closed"
        if choice=="accept" and u==m["opponent"]:
            m["status"]="playing"
            m["stage"]="pets" if m["game"]=="petfight" else "moves"
            return "ok"
        if choice=="decline" and u in (m["challenger"],m["opponent"]):
            m["status"]="declined"
            return "ok"
        return "forbidden"
    return _operate(match_id,user_id,apply)


def choose(match_id,user_id,species):
    def apply(m,u):
        if m["status"]!="playing" or m["stage"]!="pets":
            return "closed"
        side="a" if u==m["challenger"] else "b"
        if side in m["data"]["pets"]:
            return "already"
        with connect() as db:
            pet=db.execute("SELECT name FROM pets WHERE user_id=? AND species=?",(u,species)).fetchone()
        if not pet:
            return "not_owned"
        m["data"]["pets"][side]={"species":species,"name":pet["name"]}
        if len(m["data"]["pets"])==2:
            m["stage"]="moves"
        return "picked"
    return _operate(match_id,user_id,apply)


def move(match_id,user_id,choice):
    def apply(m,u):
        if m["status"]!="playing" or m["stage"]!="moves":
            return "closed"
        if choice not in MOVES[m["game"]]:
            return "invalid"
        side="a" if u==m["challenger"] else "b"
        picks=m["data"]["choices"]
        if side in picks:
            return "already"
        if m["game"]=="petfight" and choice!="guard" and m["data"]["stamina"][side]==0:
            return "stamina"
        picks[side]=choice
        if len(picks)<2:
            return "waiting"
        a,b=picks["a"],picks["b"]
        m["data"]["choices"]={}
        if m["game"]=="rps":
            outcome=0 if a==b else (1 if (a,b) in (("rock","scissors"),("paper","rock"),("scissors","paper")) else 2)
            if outcome==1:
                m["score_a"]+=1
            elif outcome==2:
                m["score_b"]+=1
            m["data"]["last"]=f"{a} vs {b} • " + ("tie" if not outcome else f"<@{m['challenger'] if outcome==1 else m['opponent']}> wins")
            finish=m["score_a"]>=3 or m["score_b"]>=3
        else:
            hp=m["data"]["hp"]
            sp=m["data"]["stamina"]
            def damage(attack,defense):
                if attack=="guard":
                    return 0
                if attack=="strike":
                    return 1 if defense=="guard" else 3
                return 3 if defense=="guard" else (1 if defense=="strike" else 2)
            hp["a"]=max(0,hp["a"]-damage(b,a))
            hp["b"]=max(0,hp["b"]-damage(a,b))
            for side,act in (("a",a),("b",b)):
                sp[side]=min(3,sp[side]+2) if act=="guard" else sp[side]-1
            m["data"]["last"]=f"{a} vs {b} • {hp['a']}–{hp['b']} hp"
            finish=min(hp.values())==0 or m["round"]>=15
        if finish:
            if m["game"]=="rps":
                x,y=m["score_a"],m["score_b"]
            else:
                x,y=m["data"]["hp"]["a"],m["data"]["hp"]["b"]
            m["winner"]=m["challenger"] if x>y else (m["opponent"] if y>x else 0)
            m["status"]="finished"
            m["stage"]="done"
            return "finished"
        m["round"]+=1
        return "round"
    return _operate(match_id,user_id,apply)


def forfeit(match_id,user_id):
    def apply(m,u):
        if m["status"]!="playing":
            return "closed"
        m["winner"]=m["opponent"] if u==m["challenger"] else m["challenger"]
        m["status"]="finished"
        m["stage"]="done"
        m["data"]["last"]=f"<@{u}> forfeited"
        return "finished"
    return _operate(match_id,user_id,apply)


def records(guild_id,user_id):
    with connect() as con:
        rows=con.execute("""SELECT game,challenger,opponent,winner FROM arcade_matches
            WHERE guild_id=? AND status='finished' AND (challenger=? OR opponent=?)""",
            (guild_id,user_id,user_id)).fetchall()
    out={game:{"wins":0,"losses":0,"draws":0} for game in GAMES}
    for row in rows:
        item=out[row["game"]]
        item["draws" if row["winner"]==0 else ("wins" if row["winner"]==user_id else "losses")]+=1
    return out
