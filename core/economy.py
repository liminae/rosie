import math
import re
import sqlite3

from core import database
import sys
import time
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

FILE=Path(__file__).resolve().parents[1]/"rosie_economy.db"
WALLET=Path(__file__).resolve().parents[1]/"rosie.db"
GAMES=Path(__file__).resolve().parents[1]/"rosie_games.db"
ET=ZoneInfo("America/New_York")
RAW=sqlite3.connect
INSTALLED=False
FAILED=[]
SKIP={"give","take","transfer","economy","control","roses"}


def src():
    frame=sys._getframe(2)
    fallback="other"

    while frame:
        path=str(frame.f_code.co_filename).replace("\\","/")
        name=Path(path).stem

        if "/commands/" in path:
            fn=frame.f_code.co_name
            return f"{name}:{fn}" if fn not in ("<module>","setup") else name

        if name in ("database","casino","petbuff","brewing","roots","thornfield","soaring"):
            fallback=name

        frame=frame.f_back

    return fallback


def raw(path,timeout=10):
    con=RAW(path,timeout=timeout)
    con.row_factory=sqlite3.Row
    return con

def walletparams(sql,parameters):
    if re.search(r"\b(?:[a-z_][a-z0-9_]*\.)?wallets\b",str(sql).casefold()):
        return database.walletparams(parameters)
    return parameters

def log(rows):
    payload=FAILED+list(rows)

    if not payload:
        return

    FAILED.clear()

    try:
        with raw(FILE,30) as con:
            con.executemany(
                "INSERT INTO economy_flow(at,source,guild_id,user_id,roses,rings) VALUES(?,?,?,?,?,?)",
                payload
            )
    except sqlite3.Error as error:
        FAILED.extend(payload)
        print(f"economy tracking error ⊹ {error}")


class Connection(sqlite3.Connection):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self._economy=[]

    def snap(self,table):
        try:
            if table in ("wallets","econ.wallets"):
                rows=sqlite3.Connection.execute(
                    self,
                    f"SELECT guild_id,user_id,roses,rings FROM {table}"
                ).fetchall()

                return {
                    (int(row[0]),int(row[1])):(int(row[2]),int(row[3]))
                    for row in rows
                }

            rows=sqlite3.Connection.execute(
                self,
                f"SELECT id,roses,rings FROM {table}"
            ).fetchall()

        except sqlite3.Error:
            return None

        return {
            int(row[0]):(int(row[1]),int(row[2]))
            for row in rows
        }

    def table(self,sql):
        text=" ".join(str(sql).lower().split())

        if not text.startswith(("insert","update","delete","replace")):
            return None

        if re.search(r"\becon\.wallets\b",text):
            return "econ.wallets"

        if re.search(r"\b(?:update|into|from) wallets\b",text):
            return "wallets"

        if re.search(r"\becon\.users\b",text):
            return "econ.users"

        if re.search(r"\b(?:update|into|from) users\b",text):
            return "users"

        return None

    def diff(self,before,after,source):
        if before is None or after is None:
            return

        now=time.time()
        users=set(before)|set(after)

        for key in users:
            old=before.get(key,(0,0))
            new=after.get(key,(0,0))
            roses=new[0]-old[0]
            rings=new[1]-old[1]

            if roses or rings:
                if isinstance(key,tuple):
                    guild_id,user_id=key
                else:
                    guild_id=None
                    user_id=key

                self._economy.append(
                    (
                        now,
                        source,
                        guild_id,
                        user_id,
                        roses,
                        rings
                    )
                )

    def execute(self,sql,parameters=()):
        parameters=walletparams(sql,parameters)
        table=self.table(sql)
        before=self.snap(table) if table else None
        source=src() if table else None
        cur=sqlite3.Connection.execute(self,sql,parameters)

        if table:
            self.diff(before,self.snap(table),source)

        return cur

    def executemany(self,sql,seq_of_parameters):
        values=[
            walletparams(sql,parameters)
            for parameters in seq_of_parameters
        ]
        table=self.table(sql)
        before=self.snap(table) if table else None
        source=src() if table else None
        cur=sqlite3.Connection.executemany(self,sql,values)

        if table:
            self.diff(before,self.snap(table),source)

        return cur

    def cursor(self,*args,**kwargs):
        kwargs.setdefault("factory",Cursor)
        return sqlite3.Connection.cursor(self,*args,**kwargs)

    def flush(self):
        if not self._economy:
            return

        rows=self._economy
        self._economy=[]
        log(rows)

    def commit(self):
        sqlite3.Connection.commit(self)
        self.flush()

    def rollback(self):
        sqlite3.Connection.rollback(self)
        self._economy=[]

    def __exit__(self,kind,value,tb):
        try:
            result=sqlite3.Connection.__exit__(self,kind,value,tb)
        except Exception:
            self._economy=[]
            raise

        if kind is None:
            self.flush()
        else:
            self._economy=[]

        return result


class Cursor(sqlite3.Cursor):
    def execute(self,sql,parameters=()):
        parameters=walletparams(sql,parameters)
        con=self.connection
        table=con.table(sql) if isinstance(con,Connection) else None
        before=con.snap(table) if table else None
        source=src() if table else None
        cur=sqlite3.Cursor.execute(self,sql,parameters)

        if table:
            con.diff(before,con.snap(table),source)

        return cur

    def executemany(self,sql,seq_of_parameters):
        values=[
            walletparams(sql,parameters)
            for parameters in seq_of_parameters
        ]
        con=self.connection
        table=con.table(sql) if isinstance(con,Connection) else None
        before=con.snap(table) if table else None
        source=src() if table else None
        cur=sqlite3.Cursor.executemany(self,sql,values)

        if table:
            con.diff(before,con.snap(table),source)

        return cur


def connect(*args,**kwargs):
    if kwargs.get("factory") is not None:
        return RAW(*args,**kwargs)

    kwargs["factory"]=Connection
    return RAW(*args,**kwargs)


def install():
    global INSTALLED

    if INSTALLED:
        return

    try:
        from core import privateconfig
        privateconfig.apply()
    except ImportError:
        pass

    sqlite3.connect=connect
    INSTALLED=True


def wallet(guild_id=None):
    guild_id=database.walletscope(guild_id)
    try:
        with raw(WALLET) as con:
            if guild_id is None:
                rows=con.execute(
                    """SELECT
                        user_id,
                        SUM(roses) AS roses,
                        SUM(rings) AS rings
                    FROM wallets
                    GROUP BY user_id"""
                ).fetchall()
            else:
                rows=con.execute(
                    """SELECT
                        user_id,
                        roses,
                        rings
                    FROM wallets
                    WHERE guild_id=?""",
                    (
                        guild_id,
                    )
                ).fetchall()

    except sqlite3.Error:
        return {}

    return {
        int(row["user_id"]):(
            int(row["roses"]),
            int(row["rings"])
        )
        for row in rows
    }


def totals(data=None):
    data=data if data is not None else wallet()
    return (
        sum(value[0] for value in data.values()),
        sum(value[1] for value in data.values())
    )


def init():
    now=time.time()

    with raw(FILE) as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("""CREATE TABLE IF NOT EXISTS economy_meta(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS economy_flow(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            at REAL NOT NULL,
            source TEXT NOT NULL,
            guild_id INTEGER,
            user_id INTEGER NOT NULL,
            roses INTEGER NOT NULL DEFAULT 0,
            rings INTEGER NOT NULL DEFAULT 0
        )""")

        cols={
            row[1]
            for row in con.execute(
                "PRAGMA table_info(economy_flow)"
            )
        }

        if "guild_id" not in cols:
            con.execute(
                "ALTER TABLE economy_flow ADD COLUMN guild_id INTEGER"
            )

        con.execute("CREATE INDEX IF NOT EXISTS economy_flow_at ON economy_flow(at)")
        con.execute("CREATE INDEX IF NOT EXISTS economy_flow_source ON economy_flow(source,at)")
        con.execute("CREATE INDEX IF NOT EXISTS economy_flow_user ON economy_flow(user_id,at)")
        con.execute("CREATE INDEX IF NOT EXISTS economy_flow_guild ON economy_flow(guild_id,at)")

        started=con.execute(
            "SELECT value FROM economy_meta WHERE key='started_at'"
        ).fetchone()

        if started is None:
            roses,rings=totals()
            con.executemany(
                "INSERT INTO economy_meta(key,value) VALUES(?,?)",
                (
                    ("started_at",str(now)),
                    ("base_roses",str(roses)),
                    ("base_rings",str(rings))
                )
            )


def migrateguild(guild_id):
    with raw(FILE) as con:
        con.execute(
            """UPDATE economy_flow
            SET guild_id=?
            WHERE guild_id IS NULL""",
            (
                guild_id,
            )
        )

        con.execute(
            """INSERT INTO economy_meta(key,value)
            VALUES('legacy_guild_id',?)
            ON CONFLICT(key)
            DO UPDATE SET value=excluded.value""",
            (
                str(guild_id),
            )
        )

def mergeguilds(guild_id,shared_guild_ids=()):
    guild_id=int(guild_id)
    shared={guild_id,*map(int,shared_guild_ids)}
    with raw(FILE) as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )
        for source in sorted(shared-{guild_id}):
            con.execute(
                "UPDATE economy_flow SET guild_id=? WHERE guild_id=?",
                (guild_id,source)
            )
        con.execute(
            """INSERT INTO economy_meta(key,value)
            VALUES('legacy_guild_id',?)
            ON CONFLICT(key)
            DO UPDATE SET value=excluded.value""",
            (str(guild_id),)
        )
        con.execute(
            """INSERT INTO economy_meta(key,value)
            VALUES('shared_wallet_scope_v1',?)
            ON CONFLICT(key)
            DO UPDATE SET value=excluded.value""",
            (str(guild_id),)
        )

def meta():
    with raw(FILE) as con:
        rows=con.execute("SELECT key,value FROM economy_meta").fetchall()

    return {row["key"]:row["value"] for row in rows}


def active(days=1):
    days=max(1,int(days))
    today=datetime.now(ET).date()
    first=(today-timedelta(days=days-1)).isoformat()

    try:
        with raw(GAMES) as con:
            rows=con.execute(
                "SELECT DISTINCT user_id FROM usage_days WHERE day>=?",
                (first,)
            ).fetchall()
    except sqlite3.Error:
        return set()

    return {int(row["user_id"]) for row in rows}


def pct(values,value):
    if not values:
        return 0

    data=sorted(values)
    index=max(0,min(len(data)-1,math.ceil(len(data)*value)-1))
    return int(data[index])


def concentration(values):
    values=sorted((max(0,int(x)) for x in values),reverse=True)
    total=sum(values)

    if not total:
        return 0.0

    count=max(1,math.ceil(len(values)*0.1))
    return 100*sum(values[:count])/total


def period(days=7):
    info=meta()
    started=float(info.get("started_at",time.time()))
    now=time.time()
    since=max(started,now-max(1,int(days))*86400)
    today=datetime.now(ET).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
    return started,since,max(started,today),now


def flows(since,guild_id=None):
    guild_id=database.walletscope(guild_id)
    where="WHERE at>=?"
    params=[since]

    if guild_id is not None:
        where+=" AND guild_id=?"
        params.append(
            guild_id
        )

    with raw(FILE) as con:
        rows=con.execute(
            f"""SELECT source,
            SUM(CASE WHEN roses>0 THEN roses ELSE 0 END) AS rose_in,
            -SUM(CASE WHEN roses<0 THEN roses ELSE 0 END) AS rose_out,
            SUM(roses) AS rose_net,
            SUM(CASE WHEN rings>0 THEN rings ELSE 0 END) AS ring_in,
            -SUM(CASE WHEN rings<0 THEN rings ELSE 0 END) AS ring_out,
            SUM(rings) AS ring_net,
            COUNT(*) AS moves
            FROM economy_flow {where}
            GROUP BY source""",
            params
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


def combined(rows,skip=False):
    rose_in=rose_out=rose_net=ring_in=ring_out=ring_net=moves=0

    for row in rows:
        base=row["source"].split(":",1)[0]

        if skip and base in SKIP:
            continue

        rose_in+=int(row["rose_in"] or 0)
        rose_out+=int(row["rose_out"] or 0)
        rose_net+=int(row["rose_net"] or 0)
        ring_in+=int(row["ring_in"] or 0)
        ring_out+=int(row["ring_out"] or 0)
        ring_net+=int(row["ring_net"] or 0)
        moves+=int(row["moves"] or 0)

    return {
        "rose_in":rose_in,
        "rose_out":rose_out,
        "rose_net":rose_net,
        "ring_in":ring_in,
        "ring_out":ring_out,
        "ring_net":ring_net,
        "moves":moves
    }


def collapse(rows):
    out={}

    for row in rows:
        name=row["source"].split(":",1)[0]
        item=out.setdefault(name,{
            "source":name,
            "rose_in":0,
            "rose_out":0,
            "rose_net":0,
            "ring_in":0,
            "ring_out":0,
            "ring_net":0,
            "moves":0
        })

        for key in (
            "rose_in","rose_out","rose_net",
            "ring_in","ring_out","ring_net","moves"
        ):
            item[key]+=int(row[key] or 0)

    return sorted(
        out.values(),
        key=lambda row:(
            -abs(row["rose_net"])-abs(row["ring_net"])*10000,
            row["source"]
        )
    )


def reconcile(data=None,guild_id=None):
    guild_id=database.walletscope(guild_id)
    data=(
        data
        if data is not None
        else wallet(
            guild_id
        )
    )

    current_roses,current_rings=totals(
        data
    )

    info=meta()

    legacy=int(
        info.get(
            "legacy_guild_id",
            0
        )
        or 0
    )

    usebase=(
        guild_id is None
        or guild_id==legacy
    )

    base_roses=(
        int(
            float(
                info.get(
                    "base_roses",
                    current_roses
                )
            )
        )
        if usebase
        else 0
    )

    base_rings=(
        int(
            float(
                info.get(
                    "base_rings",
                    current_rings
                )
            )
        )
        if usebase
        else 0
    )

    where=(
        ""
        if guild_id is None
        else " WHERE guild_id=?"
    )

    params=(
        ()
        if guild_id is None
        else (
            guild_id,
        )
    )

    with raw(FILE) as con:
        row=con.execute(
            f"""SELECT
                COALESCE(SUM(roses),0) AS roses,
                COALESCE(SUM(rings),0) AS rings
            FROM economy_flow{where}""",
            params
        ).fetchone()

    tracked_roses=int(row["roses"])
    tracked_rings=int(row["rings"])

    return {
        "roses":current_roses-base_roses-tracked_roses,
        "rings":current_rings-base_rings-tracked_rings
    }


def userflow(user_ids,since,now,guild_id=None):
    guild_id=database.walletscope(guild_id)
    if not user_ids:
        return {
            "median_net_day":0,
            "span":max(
                0,
                now-since
            )
        }

    marks=",".join(
        "?"
        for _ in user_ids
    )

    guild=(
        ""
        if guild_id is None
        else " AND guild_id=?"
    )

    params=[
        since,
        *sorted(user_ids)
    ]

    if guild_id is not None:
        params.append(
            guild_id
        )

    with raw(FILE) as con:
        rows=con.execute(
            f"""SELECT user_id,SUM(roses) AS roses FROM economy_flow
            WHERE at>=? AND user_id IN ({marks})
            AND source NOT LIKE 'give:%'
            AND source NOT LIKE 'take:%'
            AND source NOT LIKE 'transfer:%'
            AND source NOT LIKE 'control:%'
            AND source NOT LIKE 'roses:%'
            AND source NOT IN ('give','take','transfer','economy','control','roses')
            {guild}
            GROUP BY user_id""",
            params
        ).fetchall()

    changes={int(row["user_id"]):int(row["roses"] or 0) for row in rows}
    span=max(1.0,now-since)
    days=span/86400
    daily=[changes.get(user_id,0)/days for user_id in user_ids]

    return {
        "median_net_day":int(round(pct(daily,0.5))),
        "span":span
    }


def drops(limit=5,guild_id=None):
    try:
        with raw(WALLET) as con:
            tables={row["name"] for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}

            if "drop_stock" not in tables:
                return []

            cols={row["name"] for row in con.execute("PRAGMA table_info(drop_stock)")}
            sold="sold_out_at" if "sold_out_at" in cols else "NULL AS sold_out_at"
            started="started_at" if "started_at" in cols else "NULL AS started_at"
            where=""
            params=[]

            if (
                guild_id is not None
                and "target_guild_id" in cols
            ):
                where=(
                    " WHERE target_guild_id=?"
                    " OR target_guild_id IS NULL"
                )
                params.append(
                    guild_id
                )

            params.append(
                limit
            )

            rows=con.execute(
                f"""SELECT id,reward,amount,price,ring_price,stock,remaining,status,created_at,{started},{sold}
                FROM drop_stock{where} ORDER BY id DESC LIMIT ?""",
                params
            ).fetchall()

            out=[]

            for row in rows:
                buyers=0

                if "drop_buys_v2" in tables:
                    buyers=con.execute(
                        "SELECT COUNT(*) AS n FROM drop_buys_v2 WHERE drop_id=? AND amount>0",
                        (row["id"],)
                    ).fetchone()["n"]

                item=dict(row)
                item["sold"]=max(0,int(row["stock"])-int(row["remaining"]))
                item["buyers"]=int(buyers)
                out.append(item)

            return out
    except sqlite3.Error:
        return []


def report(days=7,price=None,stock=None,guild_id=None):
    if FAILED:
        log(())

    days=max(1,min(30,int(days)))
    data=wallet(
        guild_id
    )
    total_roses,total_rings=totals(data)
    today_users=active(1)
    period_users=active(days)
    balances=[data.get(user_id,(0,0))[0] for user_id in today_users]
    started,since,today,now=period(days)
    all_rows=flows(
        since,
        guild_id
    )
    today_rows=flows(
        today,
        guild_id
    )
    source_rows=collapse(all_rows)
    organic=combined(all_rows,True)
    organic_today=combined(today_rows,True)
    check=reconcile(
        data,
        guild_id
    )
    holders=sum(rings>0 for roses,rings in data.values())
    flow=userflow(
        period_users,
        since,
        now,
        guild_id
    )

    result={
        "started":started,
        "since":since,
        "now":now,
        "wallets":len(data),
        "total_roses":total_roses,
        "total_rings":total_rings,
        "ring_holders":holders,
        "active_today":len(today_users),
        "active_period":len(period_users),
        "p50":pct(balances,0.50),
        "p75":pct(balances,0.75),
        "p90":pct(balances,0.90),
        "top10":concentration(balances),
        "today":organic_today,
        "window":organic,
        "sources":source_rows,
        "reconcile":check,
        "drops":drops(
            guild_id=guild_id
        ),
        "median_net_day":flow["median_net_day"],
        "span":max(0,now-since),
        "days":days
    }

    if price is not None:
        price=max(1,int(price))
        one=sum(value>=price for value in balances)
        two=sum(value>=price*2 for value in balances)
        three=sum(value>=price*3 for value in balances)
        median=result["p50"]
        pace=result["median_net_day"]

        result["price"]={
            "value":price,
            "stock":max(1,int(stock)) if stock is not None else None,
            "one":one,
            "two":two,
            "three":three,
            "users":len(balances),
            "median_share":100*price/median if median else None,
            "days":price/pace if pace>0 and result["span"]>=86400 else None
        }

    return result


# lifetime-economy-v2

def lifetime_state(guild_id=None):
    guild_id=database.walletscope(guild_id)
    info=meta()

    required=(
        "lifetime_started_at",
        "lifetime_start_id",
        "lifetime_base_roses",
        "lifetime_base_rings",
        "lifetime_exclude_user"
    )

    if any(
        key not in info
        for key in required
    ):
        return None

    started=float(
        info["lifetime_started_at"]
    )

    start_id=int(
        info["lifetime_start_id"]
    )

    exclude=int(
        info["lifetime_exclude_user"]
    )

    base_roses=int(
        info["lifetime_base_roses"]
    )

    base_rings=int(
        info["lifetime_base_rings"]
    )

    legacy=int(
        info.get(
            "legacy_guild_id",
            0
        )
        or 0
    )

    if (
        guild_id is not None
        and guild_id!=legacy
    ):
        base_roses=0
        base_rings=0

    data=wallet(
        guild_id
    )

    if exclude:
        data.pop(
            exclude,
            None
        )

    current_roses,current_rings=totals(
        data
    )

    where=(
        ""
        if guild_id is None
        else " AND guild_id=?"
    )

    params=[
        start_id,
        exclude
    ]

    if guild_id is not None:
        params.append(
            guild_id
        )

    with raw(FILE) as con:
        row=con.execute(
            f"""SELECT
                COALESCE(SUM(roses),0) AS roses,
                COALESCE(SUM(rings),0) AS rings,
                COUNT(*) AS moves
            FROM economy_flow
            WHERE id>?
            AND user_id<>?
            {where}""",
            params
        ).fetchone()

    tracked_roses=int(
        row["roses"] or 0
    )

    tracked_rings=int(
        row["rings"] or 0
    )

    return {
        "started":started,
        "start_id":start_id,
        "exclude":exclude,
        "base_roses":base_roses,
        "base_rings":base_rings,
        "current_roses":current_roses,
        "current_rings":current_rings,
        "tracked_roses":tracked_roses,
        "tracked_rings":tracked_rings,
        "moves":int(
            row["moves"] or 0
        ),
        "gap_roses":(
            current_roses
            -base_roses
            -tracked_roses
        ),
        "gap_rings":(
            current_rings
            -base_rings
            -tracked_rings
        )
    }
