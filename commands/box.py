import asyncio,re,secrets,sqlite3
from collections import Counter

import discord
from core import database
from core import fulfillment
from core import game
from discord import app_commands
from discord.ext import commands
from core import emoji as rosieemoji

ROLE_FALLBACK=10000
PITY={1:500,2:100,3:60,4:40,5:20}
LOCKS={}

TIERS={
    1:(2000,[
        (2300,"roses",1000,rosieemoji.ROSE + ' 1,000 roses'),
        (2700,"roses",1500,rosieemoji.ROSE + ' 1,500 roses'),
        (2650,"roses",2000,rosieemoji.ROSE + ' 2,000 roses'),
        (2200,"roses",2250,rosieemoji.ROSE + ' 2,250 roses'),
        (100,"roses",4000,rosieemoji.ROSE + ' 4,000 roses'),
        (25,"rings",1,"💍 1 ring"),
        (25,"custom_role",0,"🎨 custom role")
    ]),
    2:(10000,[
        (1900,"roses",5000,rosieemoji.ROSE + ' 5,000 roses'),
        (2400,"roses",7500,rosieemoji.ROSE + ' 7,500 roses'),
        (2800,"roses",10000,rosieemoji.ROSE + ' 10,000 roses'),
        (2500,"roses",12500,rosieemoji.ROSE + ' 12,500 roses'),
        (100,"roses",20000,rosieemoji.ROSE + ' 20,000 roses'),
        (100,"rings",1,"💍 1 ring"),
        (100,"rings",2,"💍 2 rings"),
        (75,"custom_role",0,"🎨 custom role"),
        (25,"claim",0,"🎀 profile bundle")
    ]),
    3:(50000,[
        (1500,"roses",25000,rosieemoji.ROSE + ' 25,000 roses'),
        (2250,"roses",37500,rosieemoji.ROSE + ' 37,500 roses'),
        (2975,"roses",50000,rosieemoji.ROSE + ' 50,000 roses'),
        (2750,"roses",62500,rosieemoji.ROSE + ' 62,500 roses'),
        (100,"roses",100000,rosieemoji.ROSE + ' 100,000 roses'),
        (50,"rings",1,"💍 1 ring"),
        (25,"rings",2,"💍 2 rings"),
        (225,"rings",5,"💍 5 rings"),
        (75,"custom_role",0,"🎨 custom role"),
        (25,"claim",0,"🎀 profile bundle"),
        (25,"item","nitro_basic","💙 nitro basic • 1 month")
    ]),
    4:(100000,[
        (1200,"roses",50000,rosieemoji.ROSE + ' 50,000 roses'),
        (2100,"roses",75000,rosieemoji.ROSE + ' 75,000 roses'),
        (3025,"roses",100000,rosieemoji.ROSE + ' 100,000 roses'),
        (3000,"roses",125000,rosieemoji.ROSE + ' 125,000 roses'),
        (100,"roses",200000,rosieemoji.ROSE + ' 200,000 roses'),
        (125,"rings",2,"💍 2 rings"),
        (150,"rings",5,"💍 5 rings"),
        (125,"rings",10,"💍 10 rings"),
        (100,"custom_role",0,"🎨 custom role"),
        (25,"claim",0,"🎀 profile bundle"),
        (25,"item","nitro_basic","💙 nitro basic • 1 month"),
        (25,"item","nitro","💜 nitro • 1 month")
    ]),
    5:(200000,[
        (900,"roses",100000,rosieemoji.ROSE + ' 100,000 roses'),
        (1900,"roses",150000,rosieemoji.ROSE + ' 150,000 roses'),
        (3075,"roses",200000,rosieemoji.ROSE + ' 200,000 roses'),
        (3300,"roses",250000,rosieemoji.ROSE + ' 250,000 roses'),
        (100,"roses",400000,rosieemoji.ROSE + ' 400,000 roses'),
        (200,"rings",5,"💍 5 rings"),
        (200,"rings",10,"💍 10 rings"),
        (100,"rings",20,"💍 20 rings"),
        (150,"custom_role",0,"🎨 custom role"),
        (25,"claim",0,"🎀 profile bundle"),
        (25,"item","nitro_basic","💙 nitro basic • 1 month"),
        (25,"item","nitro","💜 nitro • 1 month")
    ])
}

NUMERALS=("i","ii","iii","iv","v")



def roll(prizes):
    n=secrets.randbelow(10000)

    for chance,kind,value,name in prizes:
        if n<chance:
            return kind,value,name

        n-=chance

    raise RuntimeError(
        "invalid odds"
    )


def prizes_for(uid,tier):
    prizes=TIERS[tier][1]

    return prizes

def handler(guild,kind):
    if guild is None:
        return None

    fulfillment_kind=(
        "custom_role"
        if kind=="custom_role"
        else "profile_bundle"
    )

    return fulfillment.handler(
        guild.id,
        fulfillment_kind
    )


def handlermention(user_id):
    return (
        f"<@{user_id}>"
        if user_id
        else "waiting on fulfillment"
    )

def pityreward(tier):
    rings=[
        int(value)
        for _,kind,value,_
        in TIERS[tier][1]
        if kind=="rings"
    ]

    if not rings:
        raise RuntimeError(
            "tier has no ring prize"
        )

    return min(
        rings
    )

def pity(guild_id,uid,tier):
    limit=PITY[tier]
    guild_id=database.walletscope(
        guild_id
    )

    with sqlite3.connect(
        database.FILE,
        timeout=10
    ) as db:
        last=db.execute(
            """SELECT id FROM opens
            WHERE guild_id=?
            AND user=?
            AND tier=?
            AND LOWER(prize) LIKE '%ring%'
            ORDER BY id DESC
            LIMIT 1""",
            (
                guild_id,
                uid,
                tier
            )
        ).fetchone()

        if last:
            count=db.execute(
                """SELECT COUNT(*) FROM opens
                WHERE guild_id=?
                AND user=?
                AND tier=?
                AND id>?""",
                (
                    guild_id,
                    uid,
                    tier,
                    last[0]
                )
            ).fetchone()[0]
        else:
            count=db.execute(
                """SELECT COUNT(*) FROM opens
                WHERE guild_id=?
                AND user=?
                AND tier=?""",
                (
                    guild_id,
                    uid,
                    tier
                )
            ).fetchone()[0]

    return min(
        count,
        limit-1
    )


def role(uid):
    with sqlite3.connect(
        database.FILE,
        timeout=10
    ) as db:
        return db.execute(
            """SELECT 1 FROM claims
            WHERE user=?
            AND LOWER(prize) LIKE '%custom role%'
            LIMIT 1""",
            (uid,)
        ).fetchone() is not None

def close_claim(claim):
    with sqlite3.connect(database.FILE) as db:
        db.execute(
            "UPDATE claims SET status='closed' WHERE id=?",
            (claim,)
        )

def claim_from(channel):
    match=re.search(
        r"claim:(\d+)",
        channel.topic or ""
    )

    return (
        int(match.group(1))
        if match
        else None
    )

def handler_from(channel):
    topic=channel.topic or ""

    match=re.search(
        r"handler:(\d+)",
        topic
    )

    if match:
        return int(
            match.group(1)
        )

    return (
        handler(
            channel.guild,
            "custom_role"
        )
        if "custom role" in topic.lower()
        else handler(
            channel.guild,
            "claim"
        )
    )

class CustomRoleView(discord.ui.View):
    def __init__(self,bot):
        super().__init__(
            timeout=None
        )

        self.bot=bot

    @discord.ui.button(
        emoji="🗑️",
        style=discord.ButtonStyle.danger,
        custom_id="rosie:close_custom_role"
    )
    async def close(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        allowed=handler_from(
            it.channel
        )

        if (
            it.user.id!=allowed
            and not await self.bot.is_owner(it.user)
        ):
            await it.response.send_message(
                "nuh uh",
                ephemeral=True
            )
            return

        claim=claim_from(
            it.channel
        )

        await it.response.send_message(
            "closing heh",
            ephemeral=True
        )

        await asyncio.sleep(1)

        await it.channel.delete(
            reason=f"box claim closed by {it.user}"
        )

        if claim is not None:
            close_claim(
                claim
            )

class ConfirmView(discord.ui.View):
    def __init__(
        self,
        cog,
        user_id,
        guild_id,
        tier,
        amount
    ):
        super().__init__(
            timeout=60
        )

        self.cog=cog
        self.user_id=user_id
        self.guild_id=guild_id
        self.tier=tier
        self.amount=amount
        self.done=False
        self.message=None

    def embed(self,expired=False):
        cost,_=TIERS[
            self.tier
        ]

        if expired:
            return discord.Embed(
                title="📦 box wandered off",
                description="run `/box` again if u still want it",
                color=discord.Color.dark_red()
            )

        total=(
            cost
            *self.amount
        )

        limit=PITY[
            self.tier
        ]

        title=(
            f"📦 tier "
            f"{NUMERALS[self.tier-1]} mystery "
            f"{'box' if self.amount==1 else 'boxes'}"
        )

        text=(
            f'amount ⊹ **{self.amount:,}**\ncost ⊹ **{total:,} roses** {rosieemoji.ROSE}\npity ⊹ **{pity(self.guild_id, self.user_id, self.tier)} / {limit}**\nsee what could be yours in `/odds`'
        )

        return discord.Embed(
            title=title,
            description=text,
            color=discord.Color.dark_red()
        )

    async def check(self,it):

        if it.user.id!=self.user_id:
            await it.response.send_message(
                "not ur box babe",
                ephemeral=True
            )
            return False

        if self.done:
            await it.response.send_message(
                "already handled",
                ephemeral=True
            )
            return False

        return True

    @discord.ui.button(
        emoji="✅",
        style=discord.ButtonStyle.success
    )
    async def yes(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        if not await self.check(it):
            return

        self.done=True

        cost,_=TIERS[
            self.tier
        ]

        total=(
            cost
            *self.amount
        )

        roses,_=database.wallet(
            it.guild.id,
            self.user_id
        )

        if roses<total:
            await it.response.edit_message(
                embed=discord.Embed(
                    title="📦 nvm ur broke",
                    description=(
                        f'need **{total - roses:,} more roses {rosieemoji.ROSE}**'
                    ),
                    color=discord.Color.dark_red()
                ),
                view=None
            )
            return

        title=(
            "📦 opening..."
            if self.amount==1
            else f"📦 opening {self.amount:,} boxes..."
        )

        await it.response.edit_message(
            embed=discord.Embed(
                title=title,
                description="rosie says good luck",
                color=discord.Color.dark_red()
            ),
            view=None
        )

        await self.cog.batch(
            it,
            self.tier,
            self.amount
        )

    @discord.ui.button(
        emoji="❌",
        style=discord.ButtonStyle.secondary
    )
    async def no(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        if not await self.check(it):
            return

        self.done=True

        await it.response.edit_message(
            embed=discord.Embed(
                title="📦 canceled",
                description='roses stay put ' + rosieemoji.ROSE,
                color=discord.Color.dark_red()
            ),
            view=None
        )

    async def on_timeout(self):
        if (
            self.done
            or self.message is None
        ):
            return

        self.done=True

        for item in self.children:
            item.disabled=True

        try:
            await self.message.edit(
                embed=self.embed(True),
                view=self
            )
        except discord.HTTPException:
            pass

class Box(commands.Cog):
    def __init__(self,bot):
        self.bot=bot

    async def announce(
        self,
        it,
        text
    ):
        message=(
            f"📦 "
            f"{it.user.mention} "
            f"⊹ "
            f"{text}"
        )

        if it.channel is None:
            await it.followup.send(
                message,
                ephemeral=False,
                allowed_mentions=discord.AllowedMentions.none()
            )
            return

        await it.channel.send(
            message,
            allowed_mentions=discord.AllowedMentions.none()
        )

    async def ticket(
        self,
        it,
        kind
    ):
        payout=handler(
            it.guild,
            kind
        )

        app=await self.bot.application_info()

        owner=it.guild.get_member(
            app.owner.id
        )

        if owner is None:
            try:
                owner=await it.guild.fetch_member(
                    app.owner.id
                )
            except discord.HTTPException:
                owner=None

        staff=it.guild.get_member(
            payout
        )

        if staff is None:
            try:
                staff=await it.guild.fetch_member(
                    payout
                )
            except discord.HTTPException:
                staff=None

        category=next(
            (
                item
                for item in it.guild.categories
                if item.name.lower()=="redemptions"
            ),
            None
        )

        try:
            if category is None:
                category=await it.guild.create_category(
                    "Redemptions",
                    reason="rosie redemptions"
                )
            elif category.name!="Redemptions":
                await category.edit(
                    name="Redemptions",
                    reason="rosie redemptions"
                )

            allow=discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )

            overwrites={
                it.guild.default_role:
                    discord.PermissionOverwrite(
                        view_channel=False
                    ),
                it.guild.me:allow,
                it.user:allow
            }

            if owner is not None:
                overwrites[owner]=allow

            if staff is not None:
                overwrites[staff]=allow

            return await it.guild.create_text_channel(
                f"redeem-{it.user.id}",
                category=category,
                overwrites=overwrites,
                reason=f"box claim won by {it.user}"
            )

        except discord.HTTPException:
            return None

    async def receipt(
        self,
        it,
        kind,
        name,
        claim,
        channel
    ):
        payout=handler(
            it.guild,
            kind
        )

        instruction=(
            "give a name and hex code for your role"
            if kind=="custom_role"
            else "name the exact bundle you want"
        )

        try:
            await channel.edit(
                name=f"redeem-{claim}",
                topic=(
                    f"claim:{claim} • "
                    f"user:{it.user.id} • "
                    f"handler:{payout} • "
                    f"prize:{name}"
                )
            )
        except discord.HTTPException:
            pass

        receipt=await channel.send(
            f"🎟️ **redemption #{claim}**\n"
            f"winner • "
            f"{it.user.mention} "
            f"(`{it.user.id}`)\n"
            f"prize • "
            f"**{name}**\n"
            f"{instruction}\n\n"
            f"<@{payout}> pay up ahaha",
            view=CustomRoleView(
                self.bot
            )
        )

        try:
            await receipt.pin(
                reason="redemption receipt"
            )
        except discord.HTTPException:
            pass

    async def show(
        self,
        it,
        result
    ):
        name=result["name"]
        kind=result["kind"]

        if result["repeat"]:
            await self.announce(
                it,
                '**🎨 custom role**\ngreedy ahh ✦ **+10,000 roses ' + rosieemoji.ROSE + '**'
            )

        elif kind in (
            "custom_role",
            "claim"
        ):
            await self.announce(
                it,
                f"**{name}**\n"
                f"ticket made ⊹ "
                f"{result['channel'].mention}"
            )

        elif kind=="rings":
            if result["forced"]:
                await self.announce(
                    it,
                    f"**{name}** pity ✦"
                )
            else:
                await self.announce(
                    it,
                    f"**{name}**\n"
                    "shiny hehe"
                )

        elif kind=="item":
            await self.announce(
                it,
                f"**{name}**\n"
                "saved to `/balance`"
            )

        else:
            await self.announce(
                it,
                f"**{name}**"
            )

    async def one(
        self,
        it,
        tier
    ):
        cost,_=TIERS[
            tier
        ]

        prizes=prizes_for(
            it.user.id,
            tier
        )

        limit=PITY[
            tier
        ]

        reward=pityreward(
            tier
        )

        forced=(
            pity(it.guild.id,it.user.id,tier)
            >=limit-1
        )

        if forced:
            kind="rings"
            value=reward
            name=(
                f"💍 {reward} "
                f"{'ring' if reward==1 else 'rings'}"
            )
        else:
            kind,value,name=roll(
                prizes
            )

        repeat=(
            kind=="custom_role"
            and role(it.user.id)
        )

        channel=None

        if (
            kind=="claim"
            or (
                kind=="custom_role"
                and not repeat
            )
        ):
            channel=await self.ticket(
                it,
                kind
            )

            if channel is None:
                return {
                    "ok":False,
                    "reason":"ticket"
                }

        if repeat:
            claim=database.box(
                it.guild.id,
                it.user.id,
                tier,
                cost,
                "roses",
                ROLE_FALLBACK,
                '🎨 custom role → ' + rosieemoji.ROSE + ' 10,000 roses'
            )
        else:
            claim=database.box(
                it.guild.id,
                it.user.id,
                tier,
                cost,
                kind,
                value,
                name
            )

        if claim is None:
            if channel is not None:
                try:
                    await channel.delete(
                        reason="box purchase failed"
                    )
                except discord.HTTPException:
                    pass

            return {
                "ok":False,
                "reason":"balance"
            }

        if channel is not None:
            await self.receipt(
                it,
                kind,
                name,
                claim,
                channel
            )

        return {
            "ok":True,
            "kind":kind,
            "value":value,
            "name":name,
            "forced":forced,
            "repeat":repeat,
            "channel":channel,
            "claim":claim
        }

    def summary(
        self,
        it,
        tier,
        results,
        requested
    ):
        counts=Counter()
        tickets=[]
        pity_hits=0

        for result in results:
            label=(
                '🎨 custom role ✦ ' + rosieemoji.ROSE + ' 10,000 roses'
                if result["repeat"]
                else result["name"]
            )

            counts[label]+=1

            if result["forced"]:
                pity_hits+=1

            if result["channel"] is not None:
                tickets.append(
                    result["channel"].mention
                )

        lines=[
            f"opened "
            f"**{len(results):,} "
            f"tier {NUMERALS[tier-1]} boxes**"
        ]

        if len(results)!=requested:
            lines.append(
                f"stopped early ⊹ "
                f"**{len(results):,}/{requested:,}**"
            )

        for label,count in counts.items():
            lines.append(
                f"{label} × **{count:,}**"
            )

        if pity_hits:
            lines.append(
                f"pity ✦ "
                f"**{pity_hits:,}**"
            )

        if tickets:
            shown=tickets[:8]

            text=" • ".join(
                shown
            )

            if len(tickets)>8:
                text+=(
                    f" • "
                    f"+{len(tickets)-8:,} more"
                )

            lines.append(
                f"tickets ⊹ {text}"
            )

        return "\n".join(
            lines
        )

    async def batch(
        self,
        it,
        tier,
        amount
    ):
        lock=LOCKS.setdefault(
            it.user.id,
            asyncio.Lock()
        )

        async with lock:
            results=[]
            failure=None

            for _ in range(amount):
                result=await self.one(
                    it,
                    tier
                )

                if not result["ok"]:
                    failure=result["reason"]
                    break

                results.append(
                    result
                )

            if results:
                game.touch(
                    it.user.id
                )

                game.bump(
                    it.user.id,
                    "boxes_opened",
                    len(results)
                )

            if amount==1 and results:
                await self.show(
                    it,
                    results[0]
                )

            elif results:
                await self.announce(
                    it,
                    self.summary(
                        it,
                        tier,
                        results,
                        amount
                    )
                )

            if failure=="ticket":
                await it.followup.send(
                    "ticket machine died 💔 "
                    "stopped the batch",
                    ephemeral=True
                )

            elif failure=="balance":
                roses,_=database.wallet(
                    it.guild.id,
                    it.user.id
                )

                await it.followup.send(
                    f"balance moved while u blinked 💔 "
                    f"stopped with "
                    f"{roses:,} roses",
                    ephemeral=True
                )

    @app_commands.command(
        name="box",
        description="open a mystery box"
    )
    @app_commands.guild_only()
    @app_commands.choices(
        tier=[
            app_commands.Choice(
                name="tier i • 2,000 roses",
                value=1
            ),
            app_commands.Choice(
                name="tier ii • 10,000 roses",
                value=2
            ),
            app_commands.Choice(
                name="tier iii • 50,000 roses",
                value=3
            ),
            app_commands.Choice(
                name="tier iv • 100,000 roses",
                value=4
            ),
            app_commands.Choice(
                name="tier v • 200,000 roses",
                value=5
            )
        ]
    )
    @app_commands.describe(
        amount='amount'
    )
    async def box(
        self,
        it:discord.Interaction,
        tier:app_commands.Choice[int],
        amount:int=1
    ):

        if amount<1:
            await it.response.send_message(
                "amount gotta be at least 1",
                ephemeral=True
            )
            return

        cost,_=TIERS[
            tier.value
        ]

        total=(
            cost
            *amount
        )

        roses,_=database.wallet(
            it.guild.id,
            it.user.id
        )

        if roses<total:
            await it.response.send_message(
                f'broke broski you need {total - roses:,} more {rosieemoji.ROSE}',
                ephemeral=True
            )
            return

        view=ConfirmView(
            self,
            it.user.id,
            it.guild.id,
            tier.value,
            amount
        )

        await it.response.send_message(
            embed=view.embed(),
            view=view,
            ephemeral=True
        )

        view.message=await it.original_response()

async def setup(bot):
    bot.add_view(
        CustomRoleView(bot)
    )

    await bot.add_cog(
        Box(bot)
    )
