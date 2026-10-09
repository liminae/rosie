import sys
sys.dont_write_bytecode=True

import asyncio
import os
import secrets
import sqlite3
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from aiohttp import ClientSession,web

try:
    from . import soaring
except ImportError:
    import soaring


ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from core import seasonal
DIST=Path(__file__).resolve().parent/"dist"
DB=ROOT/"rosie.db"
seasonal.database.FILE=str(DB)
ET=ZoneInfo("America/New_York")

CLIENT_ID=os.environ.get("DISCORD_CLIENT_ID","")
CLIENT_SECRET=os.environ.get("DISCORD_CLIENT_SECRET","")
BOT_TOKEN=os.environ.get("DISCORD_TOKEN","")

MODES={
    "easy":(10,8,10,100),
    "medium":(18,14,40,250),
    "hard":(24,20,99,500)
}

MAX_REWARDS=3
SESSIONS={}
GAMES={}
LOCKS={}

DEATHS=(
    "the bush won. excellent gardening technique",
    "ur pattern recognition has left the server",
    "cause of death ⊹ landscaping",
    "ur obituary just says left click",
    "medical cause of death ⊹ hubris",
    "the field has been informed of your passing",
    "natural selection by landscaping",
    "rosie regrets to report the shrub won"
)

def install():
    try:
        from core import economy
        economy.init()
        economy.install()
        print("thornfield economy tracking ✓")
    except Exception as error:
        print(f"thornfield economy tracking warning: {error}")

def connect():
    con=sqlite3.connect(DB,timeout=15)
    con.row_factory=sqlite3.Row
    return con

def today():
    return datetime.now(ET).date().isoformat()

def init():
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS thorns_days(
            user_id INTEGER NOT NULL,
            day TEXT NOT NULL,
            wins INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id,day)
        )""")

def wins(uid):
    with connect() as con:
        row=con.execute(
            "SELECT wins FROM thorns_days WHERE user_id=? AND day=?",
            (uid,today())
        ).fetchone()

    return int(row["wins"]) if row else 0

def pay(guild_id,uid,amount):
    day=today()

    with connect() as con:
        con.execute("BEGIN IMMEDIATE")

        con.execute(
            "INSERT OR IGNORE INTO thorns_days(user_id,day,wins) VALUES(?,?,0)",
            (uid,day)
        )

        count=con.execute(
            "SELECT wins FROM thorns_days WHERE user_id=? AND day=?",
            (uid,day)
        ).fetchone()[0]

        if count>=MAX_REWARDS:
            return 0,count

        con.execute(
            "INSERT OR IGNORE INTO wallets(guild_id,user_id) VALUES(?,?)",
            (guild_id,uid)
        )

        con.execute(
            "UPDATE wallets SET roses=roses+? WHERE guild_id=? AND user_id=?",
            (amount,guild_id,uid)
        )

        con.execute(
            "UPDATE thorns_days SET wins=wins+1 WHERE user_id=? AND day=?",
            (uid,day)
        )

        return amount,count+1

class Board:
    def __init__(self,mode):
        self.mode=mode
        self.w,self.h,self.total,self.reward=MODES[mode]
        self.mines=None
        self.open=set()
        self.flags=set()
        self.hit=None
        self.done=False
        self.won=False
        self.started=None
        self.ended=None
        self.paid=False
        self.xp=False
        self.note=""

    def near(self,x,y):
        for ny in range(max(0,y-1),min(self.h,y+2)):
            for nx in range(max(0,x-1),min(self.w,x+2)):
                if (nx,ny)!=(x,y):
                    yield nx,ny

    def make(self,x,y):
        safe={(x,y)}
        safe.update(self.near(x,y))

        cells=[
            (cx,cy)
            for cy in range(self.h)
            for cx in range(self.w)
            if (cx,cy) not in safe
        ]

        self.mines=set(
            secrets.SystemRandom().sample(
                cells,
                self.total
            )
        )

        self.started=time.time()

    def count(self,x,y):
        if self.mines is None:
            return 0

        return sum(
            (nx,ny) in self.mines
            for nx,ny in self.near(x,y)
        )

    def flood(self,x,y):
        q=deque([(x,y)])
        seen=set()

        while q:
            cell=q.popleft()

            if (
                cell in seen
                or cell in self.flags
                or cell in self.mines
            ):
                continue

            seen.add(cell)
            self.open.add(cell)

            if self.count(*cell)==0:
                for near in self.near(*cell):
                    if (
                        near not in seen
                        and near not in self.flags
                    ):
                        q.append(near)

    def finish(self):
        if len(self.open)==self.w*self.h-self.total:
            self.done=True
            self.won=True
            self.ended=time.time()
            return True

        return False

    def reveal(self,x,y):
        cell=(x,y)

        if self.done or cell in self.flags:
            return None

        if self.mines is None:
            self.make(x,y)

        if cell in self.open:
            need=self.count(x,y)
            around=list(self.near(x,y))

            if (
                need
                and sum(
                    near in self.flags
                    for near in around
                )==need
            ):
                for near in around:
                    if (
                        near in self.flags
                        or near in self.open
                    ):
                        continue

                    if near in self.mines:
                        self.done=True
                        self.hit=near
                        self.ended=time.time()
                        return "dead"

                    self.flood(*near)

                if self.finish():
                    return "win"

            return None

        if cell in self.mines:
            self.done=True
            self.hit=cell
            self.ended=time.time()
            return "dead"

        self.flood(x,y)

        if self.finish():
            return "win"

        return None

    def flag(self,x,y):
        cell=(x,y)

        if self.done or cell in self.open:
            return

        if cell in self.flags:
            self.flags.remove(cell)
            return

        if len(self.flags)<self.total:
            self.flags.add(cell)

    def death(self):
        left=self.w*self.h-self.total-len(self.open)

        if left<=2:
            return "two squares from freedom btw. rosie thought u should know"

        if len(self.open)<=3:
            return "that was fast. the investigation has been canceled"

        if self.mode=="hard" and secrets.randbelow(3)==0:
            return "99 thorns and u found THAT one. statistically inspirational"

        return secrets.choice(DEATHS)

    def elapsed(self):
        if self.started is None:
            return 0

        end=self.ended or time.time()
        return max(0,end-self.started)

    def grid(self):
        result=[]

        for y in range(self.h):
            row=[]

            for x in range(self.w):
                cell=(x,y)

                if (
                    self.done
                    and not self.won
                    and self.mines is not None
                    and cell in self.mines
                ):
                    row.append("x" if cell==self.hit else "m")

                elif (
                    self.done
                    and cell in self.flags
                    and self.mines is not None
                    and cell not in self.mines
                ):
                    row.append("w")

                elif (
                    self.done
                    and self.won
                    and self.mines is not None
                    and cell in self.mines
                ):
                    row.append("f")

                elif cell in self.flags:
                    row.append("f")

                elif cell in self.open:
                    row.append(str(self.count(x,y)))

                else:
                    row.append("c")

            result.append(row)

        return result

    def state(self,uid):
        return {
            "mode":self.mode,
            "w":self.w,
            "h":self.h,
            "mines":self.total,
            "reward":self.reward,
            "flags":len(self.flags),
            "elapsed":self.elapsed(),
            "done":self.done,
            "won":self.won,
            "note":self.note,
            "rewards_remaining":max(0,MAX_REWARDS-wins(uid)),
            "grid":self.grid()
        }

def session(request):
    header=request.headers.get("Authorization","")

    if not header.startswith("Bearer "):
        raise web.HTTPUnauthorized()

    token=header[7:]
    found=SESSIONS.get(token)

    if (
        found is None
        or found["expires"]<time.time()
    ):
        SESSIONS.pop(token,None)
        raise web.HTTPUnauthorized()

    return found

def gamekey(auth):
    return (
        auth["instance_id"],
        auth["uid"]
    )

def output(data,status=200):
    response=web.json_response(
        data,
        status=status
    )

    response.headers["Cache-Control"]="no-store"

    return response

async def health(request):
    return output({"ok":True})

async def token(request):
    if (
        not CLIENT_ID
        or not CLIENT_SECRET
        or not BOT_TOKEN
    ):
        return output(
            {"error":"activity credentials missing"},
            500
        )

    body=await request.json()
    code=body.get("code")
    instance_id=body.get("instance_id")

    if not code:
        return output(
            {"error":"missing code"},
            400
        )

    if (
        not isinstance(instance_id,str)
        or not instance_id
    ):
        return output(
            {"error":"missing instance"},
            400
        )

    async with ClientSession() as http:
        async with http.post(
            "https://discord.com/api/oauth2/token",
            data={
                "client_id":CLIENT_ID,
                "client_secret":CLIENT_SECRET,
                "grant_type":"authorization_code",
                "code":code
            }
        ) as response:
            auth=await response.json()

        access=auth.get("access_token")

        if not access:
            return output(
                {
                    "error":"oauth exchange failed",
                    "detail":auth
                },
                400
            )

        async with http.get(
            "https://discord.com/api/users/@me",
            headers={
                "Authorization":f"Bearer {access}"
            }
        ) as response:
            user=await response.json()

        async with http.get(
            f"https://discord.com/api/v10/applications/{CLIENT_ID}/activity-instances/{instance_id}",
            headers={
                "Authorization":f"Bot {BOT_TOKEN}"
            }
        ) as response:
            instance=await response.json()

    if "id" not in user:
        return output(
            {"error":"could not verify Discord user"},
            400
        )

    uid=int(user["id"])

    if (
        str(instance.get("application_id"))!=CLIENT_ID
        or instance.get("instance_id")!=instance_id
        or str(uid) not in {
            str(value)
            for value in instance.get("users",[])
        }
    ):
        return output(
            {"error":"invalid activity instance"},
            403
        )

    location=instance.get("location") or {}
    guild_id=location.get("guild_id")

    if (
        location.get("kind")!="gc"
        or guild_id is None
    ):
        return output(
            {"error":"server activity required"},
            400
        )

    try:
        guild_id=int(guild_id)
    except Exception:
        return output(
            {"error":"invalid activity guild"},
            400
        )

    key=secrets.token_urlsafe(36)

    SESSIONS[key]={
        "uid":uid,
        "guild_id":guild_id,
        "instance_id":instance_id,
        "channel_id":location.get("channel_id"),
        "name":(
            user.get("global_name")
            or user.get("username")
            or "player"
        ),
        "expires":time.time()+43200
    }

    return output({
        "access_token":access,
        "session":key,
        "user":{
            "id":str(uid),
            "name":SESSIONS[key]["name"]
        }
    })

async def status(request):
    auth=session(request)
    uid=auth["uid"]
    key=gamekey(auth)

    return output({
        "user":{
            "id":str(uid),
            "name":auth["name"]
        },
        "rewards_remaining":max(
            0,
            MAX_REWARDS-wins(uid)
        ),
        "guild_id":str(auth["guild_id"]),
        "game":(
            GAMES[key].state(uid)
            if key in GAMES
            else None
        )
    })

async def new(request):
    auth=session(request)
    uid=auth["uid"]
    key=gamekey(auth)
    body=await request.json()
    mode=body.get("mode")

    if mode not in MODES:
        return output(
            {"error":"bad mode"},
            400
        )

    async with LOCKS.setdefault(
        key,
        asyncio.Lock()
    ):
        GAMES[key]=Board(mode)

        return output(
            GAMES[key].state(uid)
        )

async def reveal(request):
    auth=session(request)
    uid=auth["uid"]
    key=gamekey(auth)
    body=await request.json()

    try:
        x=int(body["x"])
        y=int(body["y"])
    except Exception:
        return output(
            {"error":"bad cell"},
            400
        )

    async with LOCKS.setdefault(
        key,
        asyncio.Lock()
    ):
        board=GAMES.get(key)

        if board is None:
            return output(
                {"error":"no game"},
                404
            )

        if not 0<=x<board.w or not 0<=y<board.h:
            return output(
                {"error":"bad cell"},
                400
            )

        result=board.reveal(x,y)

        if result=="dead":
            board.note=board.death()

        elif result=="win" and not board.paid:
            amount,count=pay(
                auth["guild_id"],
                uid,
                board.reward
            )

            board.paid=True

            if amount:
                board.note=(
                    f"FIELD CLEARED ⊹ +{amount:,} roses 🌹"
                )

                if count>=MAX_REWARDS:
                    board.note+=(
                        "\nyou're playing for fun now"
                    )

            else:
                board.note=(
                    "FIELD CLEARED\n"
                    "you're playing for fun now"
                )

        if board.started is not None and not board.xp:
            seasonal.commandxp(
                uid,
                "parlor"
            )
            board.xp=True

        return output(
            board.state(uid)
        )

async def flag(request):
    auth=session(request)
    uid=auth["uid"]
    key=gamekey(auth)
    body=await request.json()

    try:
        x=int(body["x"])
        y=int(body["y"])
    except Exception:
        return output(
            {"error":"bad cell"},
            400
        )

    async with LOCKS.setdefault(
        key,
        asyncio.Lock()
    ):
        board=GAMES.get(key)

        if board is None:
            return output(
                {"error":"no game"},
                404
            )

        if not 0<=x<board.w or not 0<=y<board.h:
            return output(
                {"error":"bad cell"},
                400
            )

        board.flag(x,y)

        return output(
            board.state(uid)
        )

async def soaringnew(request):
    auth=session(
        request
    )

    return output(
        soaring.start(
            auth["guild_id"],
            auth["uid"]
        )
    )

async def soaringfinish(request):
    auth=session(
        request
    )

    try:
        body=await request.json()
    except Exception:
        return output(
            {
                "error":"bad request"
            },
            400
        )

    result=soaring.finish(
        auth["guild_id"],
        auth["uid"],
        body.get(
            "run_id"
        ),
        body.get(
            "flaps"
        )
    )

    if not result["ok"]:
        return output(
            {
                "error":
                    result["reason"]
            },
            400
        )

    if result.pop("new",False):
        seasonal.commandxp(
            auth["uid"],
            "parlor"
        )

    return output(
        result
    )

async def index(request):
    return web.FileResponse(
        DIST/"index.html"
    )

@web.middleware
async def headers(request,handler):
    response=await handler(request)
    response.headers[
        "X-Content-Type-Options"
    ]="nosniff"
    response.headers[
        "Cache-Control"
    ]="no-store, no-cache, must-revalidate, max-age=0"
    response.headers[
        "Pragma"
    ]="no-cache"
    return response

def app():
    init()
    soaring.init()
    install()

    server=web.Application(
        middlewares=[headers]
    )

    server.router.add_get(
        "/health",
        health
    )

    server.router.add_post(
        "/api/token",
        token
    )

    server.router.add_post(
        "/.proxy/api/token",
        token
    )

    server.router.add_get(
        "/api/status",
        status
    )

    server.router.add_get(
        "/.proxy/api/status",
        status
    )

    server.router.add_post(
        "/api/game/new",
        new
    )

    server.router.add_post(
        "/.proxy/api/game/new",
        new
    )

    server.router.add_post(
        "/api/game/reveal",
        reveal
    )

    server.router.add_post(
        "/.proxy/api/game/reveal",
        reveal
    )

    server.router.add_post(
        "/api/game/flag",
        flag
    )

    server.router.add_post(
        "/.proxy/api/game/flag",
        flag
    )

    server.router.add_post(
        "/api/soaring/new",
        soaringnew
    )

    server.router.add_post(
        "/.proxy/api/soaring/new",
        soaringnew
    )

    server.router.add_post(
        "/api/soaring/finish",
        soaringfinish
    )

    server.router.add_post(
        "/.proxy/api/soaring/finish",
        soaringfinish
    )

    assets=DIST/"assets"

    if assets.exists():
        server.router.add_static(
            "/assets",
            assets
        )

        server.router.add_static(
            "/.proxy/assets",
            assets
        )

    server.router.add_get(
        "/{tail:.*}",
        index
    )

    return server

if __name__=="__main__":
    web.run_app(
        app(),
        host="127.0.0.1",
        port=8765,
        access_log=None
    )
