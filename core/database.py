import sqlite3
import time

FILE="rosie.db"
ITEMS=("nitro_basic","nitro","steam_game")
WALLET_SCOPE_ID=None
WALLET_SHARED_GUILD_IDS=set()

def configurewallets(scope_id,guild_ids):
    global WALLET_SCOPE_ID
    global WALLET_SHARED_GUILD_IDS
    WALLET_SCOPE_ID=int(scope_id)
    WALLET_SHARED_GUILD_IDS={
        int(guild_id)
        for guild_id in guild_ids
    }
    WALLET_SHARED_GUILD_IDS.add(WALLET_SCOPE_ID)

def walletscope(guild_id):
    if guild_id is None:
        return None
    guild_id=int(guild_id)
    return (
        WALLET_SCOPE_ID
        if (
            WALLET_SCOPE_ID is not None
            and guild_id in WALLET_SHARED_GUILD_IDS
        )
        else guild_id
    )

def walletparams(parameters):
    if not WALLET_SHARED_GUILD_IDS:
        return parameters
    if isinstance(parameters,dict):
        return {
            key:walletscope(value)
            if isinstance(value,int)
            and value in WALLET_SHARED_GUILD_IDS
            else value
            for key,value in parameters.items()
        }
    if isinstance(parameters,(tuple,list)):
        return type(parameters)(
            walletscope(value)
            if isinstance(value,int)
            and value in WALLET_SHARED_GUILD_IDS
            else value
            for value in parameters
        )
    return parameters

def init():
    with sqlite3.connect(FILE) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY,
            roses INTEGER NOT NULL DEFAULT 0,
            rings INTEGER NOT NULL DEFAULT 0
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS wallets(
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            roses INTEGER NOT NULL DEFAULT 0,
            rings INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(guild_id,user_id)
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS wallet_meta(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS claims(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user INTEGER NOT NULL,
            prize TEXT NOT NULL,
            time INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS opens(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            user INTEGER NOT NULL,
            tier INTEGER NOT NULL,
            prize TEXT NOT NULL,
            time INTEGER NOT NULL
        )""")

        opencols={
            row[1]
            for row in db.execute(
                "PRAGMA table_info(opens)"
            )
        }

        if "guild_id" not in opencols:
            db.execute(
                "ALTER TABLE opens "
                "ADD COLUMN guild_id INTEGER"
            )

        db.execute(
            """CREATE INDEX IF NOT EXISTS opens_pity_idx
            ON opens(guild_id,user,tier,id)"""
        )
        db.execute("""CREATE TABLE IF NOT EXISTS items(
            user INTEGER NOT NULL,
            item TEXT NOT NULL,
            amount INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user,item)
        )""")
def wallet(guild_id,uid):
    guild_id=walletscope(guild_id)
    with sqlite3.connect(FILE) as db:
        db.execute("INSERT OR IGNORE INTO wallets(guild_id,user_id) VALUES(?,?)",(guild_id,uid))
        return db.execute("SELECT roses,rings FROM wallets WHERE guild_id=? AND user_id=?",(guild_id,uid)).fetchone()

def walletadd(guild_id,uid,roses=0,rings=0):
    guild_id=walletscope(guild_id)
    with sqlite3.connect(FILE) as db:
        db.execute("INSERT OR IGNORE INTO wallets(guild_id,user_id) VALUES(?,?)",(guild_id,uid))
        db.execute("UPDATE wallets SET roses=roses+?,rings=rings+? WHERE guild_id=? AND user_id=?",(roses,rings,guild_id,uid))

def migratewallets(guild_id,shared_guild_ids=()):
    guild_id=int(guild_id)
    shared={guild_id,*map(int,shared_guild_ids)}
    with sqlite3.connect(FILE) as db:
        db.execute("BEGIN IMMEDIATE")
        legacy=db.execute("SELECT value FROM wallet_meta WHERE key='legacy_guild_id'").fetchone()
        seeded=int(legacy[0]) if legacy else None
        if seeded is not None and seeded not in shared:
            raise RuntimeError("legacy wallet guild mismatch")
        merged=db.execute("SELECT value FROM wallet_meta WHERE key='shared_wallet_scope_v1'").fetchone()
        if merged is not None and int(merged[0])!=guild_id:
            raise RuntimeError("shared wallet scope mismatch")
        if merged is None and seeded is None:
            db.execute(
                """INSERT INTO wallets(guild_id,user_id,roses,rings)
                SELECT ?,id,roses,rings FROM users
                WHERE 1
                ON CONFLICT(guild_id,user_id) DO UPDATE SET
                    roses=wallets.roses+excluded.roses,
                    rings=wallets.rings+excluded.rings""",
                (guild_id,)
            )
        for source in sorted(shared-{guild_id}):
            db.execute(
                """INSERT INTO wallets(guild_id,user_id,roses,rings)
                SELECT ?,user_id,roses,rings
                FROM wallets
                WHERE guild_id=?
                AND 1
                ON CONFLICT(guild_id,user_id) DO UPDATE SET
                    roses=wallets.roses+excluded.roses,
                    rings=wallets.rings+excluded.rings""",
                (guild_id,source)
            )
            db.execute("DELETE FROM wallets WHERE guild_id=?",(source,))
        if seeded is not None and seeded!=guild_id:
            db.execute(
                """INSERT INTO wallet_meta(key,value) VALUES('legacy_guild_id',?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
                (str(guild_id),)
            )
        elif seeded is None:
            db.execute("INSERT INTO wallet_meta(key,value) VALUES('legacy_guild_id',?)",(str(guild_id),))
        db.execute(
            """INSERT INTO wallet_meta(key,value) VALUES('shared_wallet_scope_v1',?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
            (str(guild_id),)
        )
        return merged is None

def get(uid):
    with sqlite3.connect(FILE) as db:
        db.execute("INSERT OR IGNORE INTO users(id) VALUES(?)",(uid,))
        return db.execute("SELECT roses,rings FROM users WHERE id=?",(uid,)).fetchone()

def add(uid,roses=0,rings=0):
    with sqlite3.connect(FILE) as db:
        db.execute("INSERT OR IGNORE INTO users(id) VALUES(?)",(uid,))
        db.execute("UPDATE users SET roses=roses+?,rings=rings+? WHERE id=?",(roses,rings,uid))

def holdings(uid):
    data={item:0 for item in ITEMS}
    with sqlite3.connect(FILE) as db:
        db.execute("INSERT OR IGNORE INTO users(id) VALUES(?)",(uid,))
        for item,amount in db.execute("SELECT item,amount FROM items WHERE user=?",(uid,)):
            if item in data:
                data[item]=amount
    return data

def item(uid,name):
    return holdings(uid).get(name,0)

def add_item(uid,name,amount=1):
    if name not in ITEMS:
        raise ValueError("invalid item")
    with sqlite3.connect(FILE) as db:
        db.execute("INSERT OR IGNORE INTO users(id) VALUES(?)",(uid,))
        db.execute("INSERT INTO items(user,item,amount) VALUES(?,?,?) ON CONFLICT(user,item) DO UPDATE SET amount=amount+excluded.amount",(uid,name,amount))

def box(guild_id,uid,tier,cost,kind,value,name):
    guild_id=walletscope(guild_id)
    with sqlite3.connect(FILE) as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT OR IGNORE INTO wallets(guild_id,user_id) VALUES(?,?)",(guild_id,uid))
        roses=db.execute("SELECT roses FROM wallets WHERE guild_id=? AND user_id=?",(guild_id,uid)).fetchone()[0]
        if roses<cost:
            return None
        db.execute("UPDATE wallets SET roses=roses-? WHERE guild_id=? AND user_id=?",(cost,guild_id,uid))
        claim=0
        if kind=="roses":
            db.execute("UPDATE wallets SET roses=roses+? WHERE guild_id=? AND user_id=?",(value,guild_id,uid))
        elif kind=="rings":
            db.execute("UPDATE wallets SET rings=rings+? WHERE guild_id=? AND user_id=?",(value,guild_id,uid))
        elif kind=="item":
            if value not in ITEMS:
                raise ValueError("invalid item")
            db.execute("INSERT INTO items(user,item,amount) VALUES(?,?,1) ON CONFLICT(user,item) DO UPDATE SET amount=amount+1",(uid,value))
        else:
            cur=db.execute("INSERT INTO claims(user,prize,time) VALUES(?,?,?)",(uid,name,int(time.time())))
            claim=cur.lastrowid
        db.execute(
            """INSERT INTO opens(
                guild_id,user,tier,prize,time
            ) VALUES(?,?,?,?,?)""",
            (
                guild_id,
                uid,
                tier,
                name,
                int(time.time())
            )
        )
        return claim

def redeem(guild_id,uid,rings):
    guild_id=walletscope(guild_id)
    with sqlite3.connect(FILE) as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT OR IGNORE INTO wallets(guild_id,user_id) VALUES(?,?)",(guild_id,uid))
        balance=db.execute("SELECT rings FROM wallets WHERE guild_id=? AND user_id=?",(guild_id,uid)).fetchone()[0]
        if balance<rings:
            return None
        db.execute("UPDATE wallets SET rings=rings-? WHERE guild_id=? AND user_id=?",(rings,guild_id,uid))
        prize=f"{rings*100:,} robux"
        cur=db.execute("INSERT INTO claims(user,prize,time) VALUES(?,?,?)",(uid,prize,int(time.time())))
        return cur.lastrowid

def redeem_item(uid,name,amount,label):
    if name not in ITEMS:
        raise ValueError("invalid item")
    with sqlite3.connect(FILE) as db:
        db.execute("BEGIN IMMEDIATE")
        row=db.execute("SELECT amount FROM items WHERE user=? AND item=?",(uid,name)).fetchone()
        balance=row[0] if row else 0
        if balance<amount:
            return None
        db.execute("UPDATE items SET amount=amount-? WHERE user=? AND item=?",(amount,uid,name))
        prize=label if amount==1 else f"{amount}x {label}"
        cur=db.execute("INSERT INTO claims(user,prize,time) VALUES(?,?,?)",(uid,prize,int(time.time())))
        return cur.lastrowid

def close_claim(claim):
    with sqlite3.connect(FILE) as db:
        cur=db.execute("UPDATE claims SET status='closed' WHERE id=? AND status='pending'",(claim,))
        return cur.rowcount>0
