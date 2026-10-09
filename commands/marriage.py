import asyncio,sqlite3,time

import discord
from core import database
from core import game
from discord import app_commands
from discord.ext import commands
from core import emoji as rosieemoji

PROPOSAL_COST=2
PROPOSAL_TTL=86400
DAY=86400
WEEK=604800
MONTH=2592000
YEAR=31536000
MAX_LEVEL=79
LEVEL_COST=5000
LOCK=asyncio.Lock()

MILESTONES=(
    (7*DAY,500,"7 days",1),
    (30*DAY,1000,"1 month",2),
    (90*DAY,1500,"3 months",4),
    (180*DAY,2000,"6 months",8),
    (YEAR,4000,"1 year",16)
)

def connect():
    con=sqlite3.connect(database.FILE,timeout=10)
    con.row_factory=sqlite3.Row
    return con

def base_time(age):
    if age<7*DAY:
        return 1
    return min(MAX_LEVEL,2+int((age-7*DAY)//MONTH))

def timelevel(data,now=None):
    now=time.time() if now is None else now
    age=max(0,now-float(data["married_at"]))
    shift=int(data.get("time_shift",0))
    return max(1,min(MAX_LEVEL,base_time(age)+shift))

def bondlevel(data):
    return max(0,int(data.get("bond",0)))

def level(data,now=None):
    return min(MAX_LEVEL,timelevel(data,now)+bondlevel(data))

def stipend(value):
    return 750+(value-1)*100

def reached(data,now=None):
    now=time.time() if now is None else now
    age=max(0,now-float(data["married_at"]))
    out=[]
    mask=int(data.get("milestones",0))

    for seconds,reward,label,bit in MILESTONES:
        if age>=seconds and not mask&bit:
            out.append((label,reward,bit))

    years=int(age//YEAR)
    last=int(data.get("anniversary_year",0))

    for year in range(max(2,last+1),years+1):
        out.append((f"{year} years",9000,0))

    return out

def nextreward(data,now=None):
    now=time.time() if now is None else now
    mask=int(data.get("milestones",0))
    options=[]

    for seconds,reward,label,bit in MILESTONES:
        if not mask&bit:
            options.append((
                float(data["married_at"])+seconds,
                label,
                reward
            ))
            break

    years=max(
        2,
        int(data.get("anniversary_year",0))+1
    )

    options.append((
        float(data["married_at"])+years*YEAR,
        f"{years} years",
        9000
    ))

    future=[
        item
        for item in options
        if item[0]>now
    ]

    return min(
        future,
        key=lambda item:item[0]
    ) if future else None

def init():
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS marriage_proposals(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            message_id INTEGER,
            proposer_id INTEGER NOT NULL,
            target_id INTEGER NOT NULL,
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS marriages(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            user1_id INTEGER NOT NULL,
            user2_id INTEGER NOT NULL,
            married_at REAL NOT NULL,
            ended_at REAL,
            manual_level INTEGER NOT NULL DEFAULT 1,
            bond INTEGER NOT NULL DEFAULT 0,
            time_shift INTEGER NOT NULL DEFAULT 0,
            milestones INTEGER NOT NULL DEFAULT 0,
            anniversary_year INTEGER NOT NULL DEFAULT 0,
            v2 INTEGER NOT NULL DEFAULT 1,
            love INTEGER NOT NULL DEFAULT 100,
            love_updated REAL NOT NULL,
            last_claim REAL NOT NULL
        )""")

        cols={
            row["name"]
            for row in con.execute(
                "PRAGMA table_info(marriages)"
            )
        }

        additions={
            "guild_id":"INTEGER",
            "bond":"INTEGER NOT NULL DEFAULT 0",
            "time_shift":"INTEGER NOT NULL DEFAULT 0",
            "milestones":"INTEGER NOT NULL DEFAULT 0",
            "anniversary_year":"INTEGER NOT NULL DEFAULT 0",
            "v2":"INTEGER NOT NULL DEFAULT 0"
        }

        for name,spec in additions.items():
            if name not in cols:
                con.execute(
                    f"ALTER TABLE marriages ADD COLUMN {name} {spec}"
                )

        now=time.time()

        rows=con.execute(
            "SELECT * FROM marriages WHERE v2=0"
        ).fetchall()

        for found in rows:
            data=dict(found)

            end=(
                float(data["ended_at"])
                if data["ended_at"] is not None
                else now
            )

            age=max(
                0,
                end-float(data["married_at"])
            )

            oldnatural=min(
                MAX_LEVEL,
                1+int(age//MONTH)
            )

            manual=max(
                1,
                int(data.get("manual_level",1))
            )

            oldlevel=min(
                MAX_LEVEL,
                max(manual,oldnatural)
            )

            bond=max(
                0,
                manual-oldnatural
            )

            shift=(
                oldlevel
                -bond
                -base_time(age)
            )

            mask=0

            for seconds,reward,label,bit in MILESTONES:
                if age>=seconds:
                    mask|=bit

            years=int(age//YEAR)

            con.execute(
                """UPDATE marriages
                SET bond=?,
                    time_shift=?,
                    milestones=?,
                    anniversary_year=?,
                    v2=1
                WHERE id=?""",
                (
                    bond,
                    shift,
                    mask,
                    years,
                    found["id"]
                )
            )

        if rows:
            print(
                f"marriage v2 migration ⊹ "
                f"{len(rows)} marriage(s) preserved"
            )

def migrateguild(guild_id):
    with connect() as con:
        con.execute("UPDATE marriages SET guild_id=? WHERE guild_id IS NULL",(guild_id,))

def row(found):
    return dict(found) if found else None

def love(marriage_id):
    now=time.time()

    with connect() as con:
        con.execute("BEGIN IMMEDIATE")

        data=con.execute(
            "SELECT * FROM marriages WHERE id=?",
            (marriage_id,)
        ).fetchone()

        if data is None:
            return None

        if data["ended_at"] is None:
            weeks=int(
                (now-data["love_updated"])//WEEK
            )

            if weeks>0:
                value=max(
                    50,
                    data["love"]-weeks
                )

                updated=(
                    data["love_updated"]
                    +weeks*WEEK
                )

                con.execute(
                    "UPDATE marriages SET love=?,love_updated=? WHERE id=?",
                    (
                        value,
                        updated,
                        marriage_id
                    )
                )

        data=con.execute(
            "SELECT * FROM marriages WHERE id=?",
            (marriage_id,)
        ).fetchone()

    return row(data)

def active(user_id):
    with connect() as con:
        found=con.execute(
            """SELECT id FROM marriages
            WHERE ended_at IS NULL
            AND (user1_id=? OR user2_id=?)
            ORDER BY id DESC LIMIT 1""",
            (
                user_id,
                user_id
            )
        ).fetchone()

    return love(found["id"]) if found else None

def marriage(marriage_id):
    return love(marriage_id)

def pending(user_id):
    now=time.time()

    with connect() as con:
        found=con.execute(
            """SELECT * FROM marriage_proposals
            WHERE status='pending'
            AND expires_at>?
            AND (proposer_id=? OR target_id=?)
            ORDER BY id DESC LIMIT 1""",
            (
                now,
                user_id,
                user_id
            )
        ).fetchone()

    return row(found)

def proposal(message_id):
    with connect() as con:
        found=con.execute(
            "SELECT * FROM marriage_proposals WHERE message_id=?",
            (message_id,)
        ).fetchone()

    return row(found)

def propose(
    guild_id,
    channel_id,
    proposer_id,
    target_id
):
    now=time.time()

    with connect() as con:
        cur=con.execute(
            """INSERT INTO marriage_proposals(
                guild_id,
                channel_id,
                proposer_id,
                target_id,
                created_at,
                expires_at
            ) VALUES(?,?,?,?,?,?)""",
            (
                guild_id,
                channel_id,
                proposer_id,
                target_id,
                now,
                now+PROPOSAL_TTL
            )
        )

        return cur.lastrowid

def message(proposal_id,message_id):
    with connect() as con:
        con.execute(
            """UPDATE marriage_proposals
            SET message_id=?
            WHERE id=?""",
            (
                message_id,
                proposal_id
            )
        )

def status(proposal_id,value):
    with connect() as con:
        con.execute(
            """UPDATE marriage_proposals
            SET status=?
            WHERE id=?""",
            (
                value,
                proposal_id
            )
        )

def accept(proposal_id):
    now=time.time()

    with connect() as con:
        con.execute("BEGIN IMMEDIATE")

        data=con.execute(
            """SELECT *
            FROM marriage_proposals
            WHERE id=?
            AND status='pending'""",
            (proposal_id,)
        ).fetchone()

        if data is None:
            return {
                "ok":False,
                "reason":"dead"
            }

        if data["expires_at"]<=now:
            con.execute(
                """UPDATE marriage_proposals
                SET status='expired'
                WHERE id=?""",
                (proposal_id,)
            )

            return {
                "ok":False,
                "reason":"expired"
            }

        for user_id in (
            data["proposer_id"],
            data["target_id"]
        ):
            found=con.execute(
                """SELECT 1
                FROM marriages
                WHERE ended_at IS NULL
                AND (
                    user1_id=?
                    OR user2_id=?
                )""",
                (
                    user_id,
                    user_id
                )
            ).fetchone()

            if found:
                con.execute(
                    """UPDATE marriage_proposals
                    SET status='failed'
                    WHERE id=?""",
                    (proposal_id,)
                )

                return {
                    "ok":False,
                    "reason":"married"
                }

        con.execute(
            "INSERT OR IGNORE INTO wallets(guild_id,user_id) VALUES(?,?)",
            (data["guild_id"],data["proposer_id"])
        )

        rings=con.execute(
            "SELECT rings FROM wallets WHERE guild_id=? AND user_id=?",
            (data["guild_id"],data["proposer_id"])
        ).fetchone()[0]

        if rings<PROPOSAL_COST:
            return {
                "ok":False,
                "reason":"broke",
                "need":PROPOSAL_COST-rings
            }

        con.execute(
            "UPDATE wallets SET rings=rings-? WHERE guild_id=? AND user_id=?",
            (
                PROPOSAL_COST,
                data["guild_id"],
                data["proposer_id"]
            )
        )

        cur=con.execute(
            """INSERT INTO marriages(
                guild_id,
                user1_id,
                user2_id,
                married_at,
                manual_level,
                bond,
                time_shift,
                milestones,
                anniversary_year,
                v2,
                love_updated,
                last_claim
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                data["guild_id"],
                data["proposer_id"],
                data["target_id"],
                now,
                1,
                0,
                0,
                0,
                0,
                1,
                now,
                now
            )
        )

        con.execute(
            """UPDATE marriage_proposals
            SET status='accepted'
            WHERE id=?""",
            (proposal_id,)
        )

        return {
            "ok":True,
            "id":cur.lastrowid,
            "user1":data["proposer_id"],
            "user2":data["target_id"]
        }

def upgrade(
    marriage_id,
    user_id,
    target
):
    now=time.time()

    with connect() as con:
        con.execute("BEGIN IMMEDIATE")

        found=con.execute(
            """SELECT *
            FROM marriages
            WHERE id=?
            AND ended_at IS NULL""",
            (marriage_id,)
        ).fetchone()

        if found is None:
            return {
                "ok":False,
                "reason":"dead"
            }

        data=dict(found)

        if user_id not in (
            data["user1_id"],
            data["user2_id"]
        ):
            return {
                "ok":False,
                "reason":"dead"
            }

        guild_id=data["guild_id"]

        if guild_id is None:
            raise RuntimeError(
                "marriage wallet guild missing"
            )

        current=level(
            data,
            now
        )

        if (
            current>=MAX_LEVEL
            or target!=current+1
        ):
            return {
                "ok":False,
                "reason":"moved"
            }

        con.execute(
            "INSERT OR IGNORE INTO wallets(guild_id,user_id) VALUES(?,?)",
            (guild_id,user_id)
        )

        roses=con.execute(
            "SELECT roses FROM wallets WHERE guild_id=? AND user_id=?",
            (guild_id,user_id)
        ).fetchone()[0]

        if roses<LEVEL_COST:
            return {
                "ok":False,
                "reason":"broke",
                "need":LEVEL_COST-roses
            }

        weeks=int(
            (now-data["love_updated"])//WEEK
        )

        value=min(
            100,
            max(
                50,
                data["love"]-weeks
            )+2
        )

        new_bond=(
            bondlevel(data)+1
        )

        con.execute(
            "UPDATE wallets SET roses=roses-? WHERE guild_id=? AND user_id=?",
            (
                LEVEL_COST,
                guild_id,
                user_id
            )
        )

        con.execute(
            """UPDATE marriages
            SET bond=?,
                manual_level=?,
                love=?,
                love_updated=?
            WHERE id=?""",
            (
                new_bond,
                target,
                value,
                now,
                marriage_id
            )
        )

        return {
            "ok":True,
            "bond":new_bond,
            "level":target
        }

def claim(marriage_id):
    now=time.time()

    with connect() as con:
        con.execute("BEGIN IMMEDIATE")

        found=con.execute(
            """SELECT *
            FROM marriages
            WHERE id=?
            AND ended_at IS NULL""",
            (marriage_id,)
        ).fetchone()

        if found is None:
            return {
                "ok":False,
                "reason":"dead"
            }

        data=dict(found)
        guild_id=data["guild_id"]

        if guild_id is None:
            raise RuntimeError(
                "marriage wallet guild missing"
            )

        weekly=(
            now
            >=float(data["last_claim"])+WEEK
        )

        milestones=reached(
            data,
            now
        )

        if not weekly and not milestones:
            nexts=[
                float(data["last_claim"])+WEEK
            ]

            reward=nextreward(
                data,
                now
            )

            if reward:
                nexts.append(
                    reward[0]
                )

            return {
                "ok":False,
                "reason":"cooldown",
                "ready":min(nexts)
            }

        user1=data["user1_id"]
        user2=data["user2_id"]

        con.execute(
            "INSERT OR IGNORE INTO wallets(guild_id,user_id) VALUES(?,?)",
            (guild_id,user1)
        )

        con.execute(
            "INSERT OR IGNORE INTO wallets(guild_id,user_id) VALUES(?,?)",
            (guild_id,user2)
        )

        total=0
        each=0
        value=data["love"]

        if weekly:
            current=level(
                data,
                now
            )

            total=stipend(
                current
            )

            each=total//2

            con.execute(
                "UPDATE wallets SET roses=roses+? WHERE guild_id=? AND user_id=?",
                (
                    each,
                    guild_id,
                    user1
                )
            )

            con.execute(
                "UPDATE wallets SET roses=roses+? WHERE guild_id=? AND user_id=?",
                (
                    each,
                    guild_id,
                    user2
                )
            )

            weeks=int(
                (
                    now-data["love_updated"]
                )//WEEK
            )

            value=min(
                100,
                max(
                    50,
                    data["love"]-weeks
                )+1
            )

        milestone_total=sum(
            reward
            for label,reward,bit
            in milestones
        )

        milestone_each=(
            milestone_total//2
        )

        if milestone_each:
            con.execute(
                "UPDATE wallets SET roses=roses+? WHERE guild_id=? AND user_id=?",
                (
                    milestone_each,
                    guild_id,
                    user1
                )
            )

            con.execute(
                "UPDATE wallets SET roses=roses+? WHERE guild_id=? AND user_id=?",
                (
                    milestone_each,
                    guild_id,
                    user2
                )
            )

        mask=int(
            data.get("milestones",0)
        )

        anniversary=int(
            data.get("anniversary_year",0)
        )

        for label,reward,bit in milestones:
            if bit:
                mask|=bit
            else:
                try:
                    anniversary=max(
                        anniversary,
                        int(label.split()[0])
                    )
                except ValueError:
                    pass

        if weekly:
            con.execute(
                """UPDATE marriages
                SET last_claim=?,
                    love=?,
                    love_updated=?,
                    milestones=?,
                    anniversary_year=?
                WHERE id=?""",
                (
                    now,
                    value,
                    now,
                    mask,
                    anniversary,
                    marriage_id
                )
            )
        else:
            con.execute(
                """UPDATE marriages
                SET milestones=?,
                    anniversary_year=?
                WHERE id=?""",
                (
                    mask,
                    anniversary,
                    marriage_id
                )
            )

        return {
            "ok":True,
            "guild_id":guild_id,
            "user1":user1,
            "user2":user2,
            "weekly":weekly,
            "each":each,
            "total":total,
            "milestones":[
                {
                    "label":label,
                    "total":reward,
                    "each":reward//2
                }
                for label,reward,bit
                in milestones
            ],
            "milestone_total":milestone_total,
            "milestone_each":milestone_each
        }

def divorce(
    marriage_id,
    user_id
):
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")

        found=con.execute(
            """SELECT *
            FROM marriages
            WHERE id=?
            AND ended_at IS NULL""",
            (marriage_id,)
        ).fetchone()

        if (
            found is None
            or user_id not in (
                found["user1_id"],
                found["user2_id"]
            )
        ):
            return None

        con.execute(
            """UPDATE marriages
            SET ended_at=?
            WHERE id=?""",
            (
                time.time(),
                marriage_id
            )
        )

        return dict(found)

def embed(data):
    now=time.time()
    t=timelevel(data,now)
    b=bondlevel(data)
    current=level(data,now)
    total=stipend(current)
    each=total//2
    married=int(data["married_at"])
    ready=float(data["last_claim"])+WEEK

    next_claim=(
        "ready"
        if now>=ready
        else f"<t:{int(ready)}:R>"
    )

    due=reached(
        data,
        now
    )

    if due:
        amount=sum(
            item[1]
            for item in due
        )

        milestone=(
            f'available ⊹ **{amount:,} roses {rosieemoji.ROSE}**'
        )
    else:
        upcoming=nextreward(
            data,
            now
        )

        milestone=(
            f'{upcoming[1]} ⊹ **{upcoming[2]:,} roses {rosieemoji.ROSE}** • <t:{int(upcoming[0])}:R>'
            if upcoming
            else "complete"
        )

    return discord.Embed(
        title="💍 marriage",
        description=(
            f"<@{data['user1_id']}> ♡ <@{data['user2_id']}>\n\nmarried ⊹ <t:{married}:D>\ntogether ⊹ <t:{married}:R>\n\nlove ⊹ **{data['love']}%**\ntime ⊹ **{t}**\nbond ⊹ **{b}**\nlevel ⊹ **{current} / {MAX_LEVEL}**\n\n**weekly stipend**\ntotal ⊹ **{total:,} roses {rosieemoji.ROSE}**\neach ⊹ **{each:,} roses {rosieemoji.ROSE}**\nnext claim ⊹ {next_claim}\n\n**milestone**\n{milestone}"
        ),
        color=discord.Color.dark_red()
    )

def proposal_embed(
    proposer,
    target,
    expires
):
    return discord.Embed(
        title="💍 proposal",
        description=(
            f"{proposer.mention} "
            f"⊹ "
            f"{target.mention}\n\n"
            f"cost ⊹ "
            f"**{PROPOSAL_COST} rings 💍**\n"
            f"expires ⊹ "
            f"<t:{int(expires)}:R>"
        ),
        color=discord.Color.dark_red()
    )

class ProposalView(discord.ui.View):
    def __init__(
        self,
        bot,
        disabled=False
    ):
        super().__init__(
            timeout=None
        )

        self.bot=bot

        if disabled:
            for item in self.children:
                item.disabled=True

    @discord.ui.button(
        label="accept",
        style=discord.ButtonStyle.success,
        custom_id="rosie:marriage:accept"
    )
    async def yes(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        data=proposal(
            it.message.id
        )

        if (
            data is None
            or data["status"]!="pending"
        ):
            await it.response.send_message(
                "proposal is dead",
                ephemeral=True
            )
            return

        if it.user.id!=data["target_id"]:
            await it.response.send_message(
                "not ur proposal",
                ephemeral=True
            )
            return

        async with LOCK:
            result=accept(
                data["id"]
            )

        if not result["ok"]:
            if result["reason"]=="broke":
                await it.response.send_message(
                    f"they need "
                    f"{result['need']:,} "
                    f"more 💍",
                    ephemeral=True
                )
                return

            title=(
                "💔 proposal expired"
                if result["reason"]=="expired"
                else "💔 somebody got married already"
            )

            await it.response.edit_message(
                embed=discord.Embed(
                    title=title,
                    color=discord.Color.dark_red()
                ),
                view=ProposalView(
                    self.bot,
                    True
                )
            )
            return

        game.touch(
            result["user1"]
        )

        game.touch(
            result["user2"]
        )

        data=marriage(
            result["id"]
        )

        await it.response.edit_message(
            embed=discord.Embed(
                title="💍 married",
                description=(
                    f"<@{data['user1_id']}> "
                    f"♡ "
                    f"<@{data['user2_id']}>\n\n"
                    f"married ⊹ "
                    f"<t:{int(data['married_at'])}:D>"
                ),
                color=discord.Color.dark_red()
            ),
            view=ProposalView(
                self.bot,
                True
            )
        )

    @discord.ui.button(
        label="reject",
        style=discord.ButtonStyle.danger,
        custom_id="rosie:marriage:reject"
    )
    async def no(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        data=proposal(
            it.message.id
        )

        if (
            data is None
            or data["status"]!="pending"
        ):
            await it.response.send_message(
                "proposal is dead",
                ephemeral=True
            )
            return

        if it.user.id!=data["target_id"]:
            await it.response.send_message(
                "not ur proposal",
                ephemeral=True
            )
            return

        status(
            data["id"],
            "rejected"
        )

        await it.response.edit_message(
            embed=discord.Embed(
                title="💔 rejected",
                description=(
                    f"<@{data['target_id']}> "
                    f"said no to "
                    f"<@{data['proposer_id']}>"
                ),
                color=discord.Color.dark_red()
            ),
            view=ProposalView(
                self.bot,
                True
            )
        )

class DivorceView(discord.ui.View):
    def __init__(
        self,
        user_id,
        marriage_id
    ):
        super().__init__(
            timeout=60
        )

        self.user_id=user_id
        self.marriage_id=marriage_id

    @discord.ui.button(
        emoji="💔",
        style=discord.ButtonStyle.danger
    )
    async def yes(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        if it.user.id!=self.user_id:
            await it.response.send_message(
                "nuh uh",
                ephemeral=True
            )
            return

        data=divorce(
            self.marriage_id,
            it.user.id
        )

        if data is None:
            await it.response.edit_message(
                content="already over",
                embed=None,
                view=None
            )
            return

        await it.response.edit_message(
            content="divorced",
            embed=None,
            view=None
        )

        await it.channel.send(
            embed=discord.Embed(
                title="💔 divorced",
                description=(
                    f"<@{data['user1_id']}> "
                    f"⊹ "
                    f"<@{data['user2_id']}>"
                ),
                color=discord.Color.dark_red()
            )
        )

    @discord.ui.button(
        label="stay married",
        style=discord.ButtonStyle.secondary
    )
    async def no(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        if it.user.id!=self.user_id:
            await it.response.send_message(
                "nuh uh",
                ephemeral=True
            )
            return

        await it.response.edit_message(
            content="cute",
            embed=None,
            view=None
        )

class BondView(discord.ui.View):
    def __init__(
        self,
        user_id,
        marriage_id,
        target
    ):
        super().__init__(
            timeout=60
        )

        self.user_id=user_id
        self.marriage_id=marriage_id
        self.target=target

    @discord.ui.button(
        emoji="🤍",
        style=discord.ButtonStyle.danger
    )
    async def yes(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        if it.user.id!=self.user_id:
            await it.response.send_message(
                "nuh uh",
                ephemeral=True
            )
            return

        result=upgrade(
            self.marriage_id,
            it.user.id,
            self.target
        )

        if not result["ok"]:
            if result["reason"]=="broke":
                await it.response.edit_message(
                    content=(
                        f"broke broski you need {result['need']:,} more {rosieemoji.ROSE}"
                    ),
                    embed=None,
                    view=None
                )
            else:
                await it.response.edit_message(
                    content="level moved while u blinked",
                    embed=None,
                    view=None
                )
            return

        await it.response.edit_message(
            content="bonded ♡",
            embed=None,
            view=None
        )

        data=marriage(
            self.marriage_id
        )

        total=stipend(
            result["level"]
        )

        each=total//2

        await it.channel.send(
            embed=discord.Embed(
                title="💍 marriage",
                description=(
                    f"<@{data['user1_id']}> ♡ <@{data['user2_id']}>\n\nbond ⊹ **{result['bond']}**\nlevel ⊹ **{result['level']} / {MAX_LEVEL}**\n{LEVEL_COST:,} roses {rosieemoji.ROSE} spent by {it.user.mention}\n\n**weekly stipend**\ntotal ⊹ **{total:,} roses {rosieemoji.ROSE}**\neach ⊹ **{each:,} roses {rosieemoji.ROSE}**"
                ),
                color=discord.Color.dark_red()
            )
        )

class Marriage(commands.Cog):
    def __init__(self,bot):
        self.bot=bot

    @app_commands.command(
        name="marriage",
        description="marriage stuff"
    )
    @app_commands.guild_only()
    @app_commands.choices(
        action=[
            app_commands.Choice(
                name="propose",
                value="propose"
            ),
            app_commands.Choice(
                name="bond",
                value="bond"
            ),
            app_commands.Choice(
                name="claim",
                value="claim"
            ),
            app_commands.Choice(
                name="divorce",
                value="divorce"
            )
        ]
    )
    async def marriage(
        self,
        it:discord.Interaction,
        action:str|None=None,
        user:discord.Member|None=None
    ):
        if action is None:
            target=user or it.user

            data=active(
                target.id
            )

            if data is None:
                await it.response.send_message(
                    f"{target.mention} has no marriage 💔",
                    ephemeral=True
                )
                return

            await it.response.send_message(
                embed=embed(data)
            )
            return

        if action=="propose":
            if user is None:
                await it.response.send_message(
                    "who babe",
                    ephemeral=True
                )
                return

            if user.id==it.user.id:
                await it.response.send_message(
                    "marrying urself is crazy",
                    ephemeral=True
                )
                return

            if user.bot:
                await it.response.send_message(
                    "leave the bot alone 😭",
                    ephemeral=True
                )
                return

            if active(it.user.id):
                await it.response.send_message(
                    "ur already married",
                    ephemeral=True
                )
                return

            if active(user.id):
                await it.response.send_message(
                    "theyre already married",
                    ephemeral=True
                )
                return

            if (
                pending(it.user.id)
                or pending(user.id)
            ):
                await it.response.send_message(
                    "somebody already has a proposal floating around",
                    ephemeral=True
                )
                return

            roses,rings=database.wallet(
                it.guild.id,
                it.user.id
            )

            if rings<PROPOSAL_COST:
                await it.response.send_message(
                    f"broke broski you need "
                    f"{PROPOSAL_COST-rings:,} "
                    f"more 💍",
                    ephemeral=True
                )
                return

            proposal_id=propose(
                it.guild.id,
                it.channel.id,
                it.user.id,
                user.id
            )

            expires=(
                time.time()
                +PROPOSAL_TTL
            )

            await it.response.send_message(
                embed=proposal_embed(
                    it.user,
                    user,
                    expires
                ),
                view=ProposalView(
                    self.bot
                )
            )

            original=await it.original_response()

            message(
                proposal_id,
                original.id
            )
            return

        if user is not None:
            await it.response.send_message(
                "user only matters for proposals or viewing",
                ephemeral=True
            )
            return

        data=active(
            it.user.id
        )

        if data is None:
            await it.response.send_message(
                "ur not married 💔",
                ephemeral=True
            )
            return

        if action=="bond":
            current=level(
                data
            )

            if current>=MAX_LEVEL:
                await it.response.send_message(
                    "already maxed ⊹ 79",
                    ephemeral=True
                )
                return

            target=current+1
            t=timelevel(data)
            b=bondlevel(data)
            total=stipend(target)
            each=total//2

            await it.response.send_message(
                embed=discord.Embed(
                    title="💍 bond",
                    description=(
                        f'time ⊹ **{t}**\nbond ⊹ {b} → **{b + 1}**\nlevel ⊹ {current} → **{target} / {MAX_LEVEL}**\ncost ⊹ **{LEVEL_COST:,} roses {rosieemoji.ROSE}**\n\n**weekly stipend at level {target}**\ntotal ⊹ **{total:,} roses {rosieemoji.ROSE}**\neach ⊹ **{each:,} roses {rosieemoji.ROSE}**'
                    ),
                    color=discord.Color.dark_red()
                ),
                view=BondView(
                    it.user.id,
                    data["id"],
                    target
                ),
                ephemeral=True
            )
            return

        if action=="claim":
            result=claim(
                data["id"]
            )

            if not result["ok"]:
                if result["reason"]=="cooldown":
                    await it.response.send_message(
                        "not yet babe\n"
                        f"next reward ⊹ "
                        f"<t:{int(result['ready'])}:R>",
                        ephemeral=True
                    )
                else:
                    await it.response.send_message(
                        "marriage vanished 💔",
                        ephemeral=True
                    )
                return

            lines=[]

            if result["weekly"]:
                lines.extend([
                    "**weekly stipend**",
                    f"total ⊹ **{result['total']:,} roses {rosieemoji.ROSE}**",
                    f"each ⊹ **{result['each']:,} roses {rosieemoji.ROSE}**",
                    "",
                    f"<@{result['user1']}> ⊹ {result['each']:,} roses {rosieemoji.ROSE}",
                    f"<@{result['user2']}> ⊹ {result['each']:,} roses {rosieemoji.ROSE}"
                ])

            for item in result["milestones"]:
                if lines:
                    lines.append("")

                lines.extend([
                    f"**✦ {item['label']} milestone**",
                    f"total ⊹ **{item['total']:,} roses {rosieemoji.ROSE}**",
                    f"<@{result['user1']}> ⊹ {item['each']:,} roses {rosieemoji.ROSE}",
                    f"<@{result['user2']}> ⊹ {item['each']:,} roses {rosieemoji.ROSE}"
                ])

            await it.response.send_message(
                embed=discord.Embed(
                    title="💍 marriage rewards",
                    description="\n".join(lines),
                    color=discord.Color.dark_red()
                )
            )
            return

        spouse=(
            data["user2_id"]
            if data["user1_id"]==it.user.id
            else data["user1_id"]
        )

        await it.response.send_message(
            embed=discord.Embed(
                title="💔 divorce",
                description=(
                    f"divorce <@{spouse}>?\n\n"
                    "time, bond, love and "
                    "stipend progress disappear"
                ),
                color=discord.Color.dark_red()
            ),
            view=DivorceView(
                it.user.id,
                data["id"]
            ),
            ephemeral=True
        )

async def setup(bot):
    init()
    bot.add_view(
        ProposalView(bot)
    )
    await bot.add_cog(
        Marriage(bot)
    )
