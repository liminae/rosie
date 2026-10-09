from pathlib import Path
from datetime import timedelta

import discord
from core import seasonal
from discord import app_commands
from discord.ext import commands
from discord.http import Route
import inspect
import io
import re
from PIL import Image,ImageDraw,ImageFont
from core import emoji as rosieemoji

ASSETS=Path(__file__).resolve().parents[1]/"assets"/"season"
ART={
    "witching hour":"witchinghour.png"
}

def art(name):
    filename=ART.get(
        str(name).strip().lower()
    )

    if filename is None:
        return None

    path=ASSETS/filename

    return path if path.exists() else None

def decorate(out,name):
    path=art(name)

    if path is not None:
        out.set_thumbnail(
            url=f"attachment://{path.name}"
        )

    return out

def image(name):
    path=art(name)

    if path is None:
        return {}

    return {
        "file":discord.File(
            path,
            filename=path.name
        )
    }

def seasonextra(track,tier,halloween):
    if not halloween:
        return "​"

    return {
        ("free",2):
            "🎃 ingredient cache",
        ("free",4):
            "🎃 jack-o'-tonic",
        ("free",6):
            "🎃 ingredient cache",
        ("free",8):
            "🕸️ spider silk",
        ("free",10):
            "🕯️ witchlight",
        ("paid",1):
            "🎃 large cache",
        ("paid",3):
            "🎃 jack-o'-tonic",
        ("paid",5):
            "🦴 marrow brew",
        ("paid",7):
            "🕸️ spider silk",
        ("paid",9):
            "🎃 large cache",
        ("paid",10):
            "🕯️ witchlight"
    }.get(
        (
            track,
            tier
        ),
        "​"
    )

def xpbar(xp):
    filled=round(
        40*max(
            0,
            min(
                1000,
                int(xp)
            )
        )/1000
    )

    return (
        "█"*filled
        +"░"*(40-filled)
    )

def pagebounds(page):
    page=max(
        0,
        min(
            3,
            int(page)
        )
    )

    first=page*3+1
    last=min(
        10,
        first+2
    )

    return (
        page,
        first,
        last
    )

def tierfield(
    out,
    tier,
    freeicon,
    paidicon,
    halloween
):
    freeextra=seasonextra(
        "free",
        tier,
        halloween
    )

    paidextra=seasonextra(
        "paid",
        tier,
        halloween
    )

    haspaidextra=(
        paidextra!="​"
    )

    if tier in (
        6,
        10
    ):
        paidline1="💍 **1 ring**"
        paidline2=(
            paidextra
            if haspaidextra
            else "​"
        )
    else:
        paidline1=paidextra
        paidline2="​"

    out.add_field(
        name=f"{freeicon} {tier:02d}",
        value=(
            f'**{seasonal.FREE[tier]:,} {rosieemoji.ROSE}**\n{freeextra}\n\u200b\n**paid**\n{paidicon} **{seasonal.PAID[tier]:,} {rosieemoji.ROSE}**\n{paidline1}\n{paidline2}'
        ),
        inline=True
    )

def preview(page=0):
    data=seasonal.preview()

    page,first,last=pagebounds(
        page
    )

    start=int(
        data["start"].timestamp()
    )

    end=int(
        data["end"].timestamp()
    )-1

    out=discord.Embed(
        title="🌙 witching hour",
        description=(
            "season 01\n"
            f"start ⊹ <t:{start}:D>\n"
            f"end ⊹ <t:{end}:D>\n\n"
            "XP ⊹ **0 / 1,000**\n"
            f"`{xpbar(0)}`"
        ),
        color=discord.Color.dark_red()
    )

    for tier in range(
        first,
        last+1
    ):
        tierfield(
            out,
            tier,
            "🔒",
            "🔒",
            True
        )

    return decorate(
        out,
        "witching hour"
    )

def mainembed(user_id,page=0):
    data=seasonal.current()

    if data is None:
        return preview(
            page
        )

    state=seasonal.state(
        user_id
    )

    page,first,last=pagebounds(
        page
    )

    start=int(
        data["start"].timestamp()
    )

    end=int(
        data["end"].timestamp()
    )-1

    out=discord.Embed(
        title=f"🌙 {data['name']}",
        description=(
            f"season {data['number']:02d}\n"
            f"start ⊹ <t:{start}:D>\n"
            f"end ⊹ <t:{end}:D>\n\n"
            f"XP ⊹ **{state['xp']:,} / 1,000**\n"
            f"`{xpbar(state['xp'])}`"
        ),
        color=discord.Color.dark_red()
    )

    for tier in range(
        first,
        last+1
    ):
        freeicon=(
            "✓"
            if (
                "free",
                tier
            ) in state["claims"]
            else (
                "◆"
                if state["tier"]>=tier
                else "•"
            )
        )

        paidicon=(
            "✓"
            if (
                "paid",
                tier
            ) in state["claims"]
            else (
                "◆"
                if (
                    state["paid"]
                    and state["tier"]>=tier
                )
                else (
                    "•"
                    if state["paid"]
                    else "🔒"
                )
            )
        )

        tierfield(
            out,
            tier,
            freeicon,
            paidicon,
            data["halloween"]
        )

    return decorate(
        out,
        data["name"]
    )

def brewembed(user_id):
    inv=seasonal.inventory(
        user_id
    )

    ingredients=" • ".join(
        f"{cfg['emoji']} "
        f"{inv['items'][key]}"
        for key,cfg
        in seasonal.INGREDIENTS.items()
    )

    lines=[]

    for key,cfg in seasonal.RECIPES.items():
        cost=" + ".join(
            f"{amount}"
            f"{seasonal.INGREDIENTS[item]['emoji']}"
            for item,amount
            in cfg["cost"].items()
        )

        lines.append(
            f"{cfg['emoji']} "
            f"**{cfg['name']}** "
            f"⊹ {cost} "
            f"⊹ **{inv['bottles'][key]} bottle(s)**\n"
            f"{cfg['text']}"
        )

    return discord.Embed(
        title="🧪 witching hour brews",
        description=(
            f"{ingredients}\n\n"
            +"\n\n".join(
                lines
            )
        ),
        color=discord.Color.dark_red()
    )

class Craft(discord.ui.Button):
    def __init__(
        self,
        user_id,
        key
    ):
        cfg=seasonal.RECIPES[
            key
        ]

        super().__init__(
            emoji=cfg["emoji"],
            style=discord.ButtonStyle.secondary,
            row=0
        )

        self.user_id=user_id
        self.key=key

    async def callback(
        self,
        it:discord.Interaction
    ):
        if it.user.id!=self.user_id:
            await it.response.send_message(
                "make ur own",
                ephemeral=True
            )
            return

        result=seasonal.brew(
            self.user_id,
            self.key
        )

        if not result["ok"]:
            if result[
                "reason"
            ]=="ingredients":
                text=(
                    "missing ⊹ "
                    +" • ".join(
                        f"{amount}"
                        f"{seasonal.INGREDIENTS[key]['emoji']}"
                        for key,amount
                        in result[
                            "missing"
                        ].items()
                    )
                )
            else:
                text="not rn"

            await it.response.send_message(
                text,
                ephemeral=True
            )
            return

        await it.response.edit_message(
            embed=brewembed(
                self.user_id
            ),
            view=BrewView(
                self.user_id
            )
        )

class Drink(discord.ui.Button):
    def __init__(
        self,
        user_id,
        key,
        amount
    ):
        cfg=seasonal.RECIPES[
            key
        ]

        super().__init__(
            emoji=cfg["emoji"],
            style=discord.ButtonStyle.secondary,
            disabled=amount<1,
            row=1
        )

        self.user_id=user_id
        self.key=key

    async def callback(
        self,
        it:discord.Interaction
    ):
        if it.user.id!=self.user_id:
            await it.response.send_message(
                "make ur own",
                ephemeral=True
            )
            return

        result=seasonal.drink(
            self.user_id,
            self.key
        )

        if not result["ok"]:
            text={
                "active":
                    "finish the active one first",
                "cap":
                    "marrow is capped today",
                "bottle":
                    "you dont have one"
            }.get(
                result["reason"],
                "not rn"
            )

            await it.response.send_message(
                text,
                ephemeral=True
            )
            return

        await it.response.edit_message(
            embed=brewembed(
                self.user_id
            ),
            view=BrewView(
                self.user_id
            )
        )

class BrewView(discord.ui.View):
    def __init__(
        self,
        user_id
    ):
        super().__init__(
            timeout=300
        )

        self.user_id=user_id
        inv=seasonal.inventory(
            user_id
        )

        for key in seasonal.RECIPES:
            self.add_item(
                Craft(
                    user_id,
                    key
                )
            )

        for key in seasonal.RECIPES:
            self.add_item(
                Drink(
                    user_id,
                    key,
                    inv[
                        "bottles"
                    ][key]
                )
            )

class BrewsButton(discord.ui.Button):
    def __init__(
        self,
        user_id
    ):
        super().__init__(
            emoji="🎃",
            style=discord.ButtonStyle.secondary
        )

        self.user_id=user_id

    async def callback(
        self,
        it:discord.Interaction
    ):
        if it.user.id!=self.user_id:
            await it.response.send_message(
                "make ur own",
                ephemeral=True
            )
            return

        await it.response.send_message(
            embed=brewembed(
                self.user_id
            ),
            view=BrewView(
                self.user_id
            ),
            ephemeral=True
        )

class Place(discord.ui.Button):
    def __init__(
        self,
        user_id,
        key,
        index
    ):
        name,emoji,_=seasonal.PLACES[
            key
        ]

        super().__init__(
            emoji=emoji,
            style=discord.ButtonStyle.secondary,
            row=(
                0
                if index<3
                else 1
            )
        )

        self.user_id=user_id
        self.key=key

    async def callback(
        self,
        it:discord.Interaction
    ):
        if it.user.id!=self.user_id:
            await it.response.send_message(
                "get ur own bad decisions",
                ephemeral=True
            )
            return

        result=seasonal.adventure(
            it.guild.id,
            self.user_id,
            self.key
        )

        if not result["ok"]:
            await it.response.send_message(
                "you already went out today",
                ephemeral=True
            )
            return

        if result[
            "kind"
        ]=="item":
            cfg=seasonal.INGREDIENTS[
                result["item"]
            ]

            reward=(
                f"**+{result['amount']} "
                f"{cfg['name'] if result['amount']==1 else cfg['plural']} "
                f"{cfg['emoji']}**"
            )

        elif result[
            "kind"
        ]=="roses":
            reward=(
                f"**+{result['amount']:,} roses {rosieemoji.ROSE}**"
            )

        else:
            reward="nothing. tragic."

        await it.response.edit_message(
            embed=discord.Embed(
                title=(
                    f"{result['emoji']} "
                    f"{result['name']}"
                ),
                description=(
                    f"{reward}\n\n"
                    f"season XP ⊹ "
                    f"**+{result['xp']}**\n"
                    "come back tomorrow"
                ),
                color=discord.Color.dark_red()
            ),
            view=None
        )

class AdventureView(discord.ui.View):
    def __init__(
        self,
        user_id
    ):
        super().__init__(
            timeout=600
        )

        for index,key in enumerate(
            seasonal.PLACES
        ):
            self.add_item(
                Place(
                    user_id,
                    key,
                    index
                )
            )

class AdventureButton(discord.ui.Button):
    def __init__(
        self,
        user_id
    ):
        super().__init__(
            emoji="🕯️",
            style=discord.ButtonStyle.secondary
        )

        self.user_id=user_id

    async def callback(
        self,
        it:discord.Interaction
    ):
        await it.response.send_message(
            embed=discord.Embed(
                title="🌙 witching hour",
                description=(
                    "pick somewhere to regret visiting"
                ),
                color=discord.Color.dark_red()
            ),
            view=AdventureView(
                self.user_id
            ),
            ephemeral=True
        )

def helpprogress(user_id):
    data=seasonal.current()

    if data is None:
        return {}

    with seasonal.connect() as con:
        rows=con.execute(
            """SELECT key,amount
            FROM season_daily
            WHERE user_id=?
            AND season=?
            AND day=?""",
            (
                user_id,
                data["id"],
                seasonal.today()
            )
        ).fetchall()

    return {
        row["key"]:int(
            row["amount"]
        )
        for row in rows
    }


def helpembed(user_id):
    used=helpprogress(
        user_id
    )

    state=seasonal.state(
        user_id
    )

    def amount(key,cap):
        return min(
            cap,
            int(
                used.get(
                    key,
                    0
                )
            )
        )

    xpkeys=[
        ("messages",10),
        ("command:daily",5),
        ("command:pluck",8),
        ("command:garden",4),
        ("command:forage",6),
        ("command:brew",4),
        ("command:quests",4),
        ("command:pet",4),
        ("command:campaign",10),
        ("command:scratch",2),
        ("command:parlor",2),
        ("marrow",20),
        ("command:boss",6),
        ("command:relic",4),
        ("command:reaper",4),
        ("command:rune",4),
        ("command:sin",4)
    ]

    todayxp=sum(
        amount(
            key,
            cap
        )
        for key,cap
        in xpkeys
    )

    paid=(
        "🔓"
        if (
            state
            and state["paid"]
        )
        else "🔒"
    )

    seasonxp=(
        int(
            state["xp"]
        )
        if state
        else 0
    )

    return discord.Embed(
        title="❓ witching hour",
        description=(
            "**progress**\n"
            f"season ⊹ **{seasonxp:,} / {seasonal.MAX_XP:,} XP**\n"
            f"today ⊹ **{todayxp:,} XP**\n\n"
            "**daily XP**\n"
            f"messages ⊹ **+1** • **{amount('messages',10)}/10**\n"
            f"`/daily` ⊹ **+5** • **{amount('command:daily',5)}/5**\n"
            f"`/pluck` ⊹ **+1** • **{amount('command:pluck',8)}/8**\n"
            f"`/garden` ⊹ **+1** • **{amount('command:garden',4)}/4**\n"
            f"`/forage` ⊹ **+1** • **{amount('command:forage',6)}/6**\n"
            f"`/brew` ⊹ **+1** • **{amount('command:brew',4)}/4**\n"
            f"`/quests` ⊹ **+2** • **{amount('command:quests',4)}/4**\n"
            f"`/pet` ⊹ **+1** • **{amount('command:pet',4)}/4**\n"
            f"`/campaign` ⊹ **+2** • **{amount('command:campaign',10)}/10**\n"
            f"`/scratch` ⊹ **+2** • **{amount('command:scratch',2)}/2**\n"
            f"`/parlor` ⊹ **+1** • **{amount('command:parlor',2)}/2**\n\n"
            "**bonus XP**\n"
            f"marrow brew ⊹ **+10** • **{amount('marrow',20)}/20**\n"
            f"`/boss` ⊹ **+3** • **{amount('command:boss',6)}/6**\n"
            f"`/relic` ⊹ **+2** • **{amount('command:relic',4)}/4**\n"
            f"`/reaper` ⊹ **+2** • **{amount('command:reaper',4)}/4**\n"
            f"`/rune` ⊹ **+2** • **{amount('command:rune',4)}/4**\n"
            f"`/sin` ⊹ **+2** • **{amount('command:sin',4)}/4**\n\n"
            f"**paid** ⊹ {paid}"
        ),
        color=discord.Color.dark_red()
    )


class HelpButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            emoji="❓",
            style=discord.ButtonStyle.secondary
        )

    async def callback(
        self,
        it:discord.Interaction
    ):
        await it.response.send_message(
            embed=helpembed(
                it.user.id
            ),
            ephemeral=True
        )


class SeasonPageButton(discord.ui.Button):
    def __init__(
        self,
        user_id,
        page,
        move,
        locked
    ):
        super().__init__(
            emoji={
                "first":"⏪",
                "prev":"◀️",
                "next":"▶️",
                "last":"⏩"
            }[move],
            style=discord.ButtonStyle.secondary,
            disabled=(
                (
                    move in (
                        "first",
                        "prev"
                    )
                    and page==0
                )
                or (
                    move in (
                        "next",
                        "last"
                    )
                    and page==3
                )
            ),
            row=0
        )

        self.user_id=user_id
        self.page=page
        self.move=move
        self.locked=locked

    async def callback(
        self,
        it:discord.Interaction
    ):
        page={
            "first":0,
            "prev":max(
                0,
                self.page-1
            ),
            "next":min(
                3,
                self.page+1
            ),
            "last":3
        }[
            self.move
        ]

        await it.response.defer()

        file=seasoncardfile(
            self.user_id,
            page,
            self.locked
        )

        await it.edit_original_response(
            embeds=[],
            attachments=[
                file
            ],
            view=(
                PreviewView(
                    self.user_id,
                    page
                )
                if self.locked
                else SeasonView(
                    self.user_id,
                    page
                )
            )
        )




class PreviewView(discord.ui.View):
    def __init__(
        self,
        user_id,
        page=0
    ):
        super().__init__(
            timeout=None
        )

        self.user_id=user_id

        for move in (
            "first",
            "prev",
            "next",
            "last"
        ):
            self.add_item(
                SeasonPageButton(
                    user_id,
                    page,
                    move,
                    True
                )
            )

        helpbutton=HelpButton()
        helpbutton.row=0
        self.add_item(
            helpbutton
        )

        state=seasonal.state(
            user_id
        )

        buy=BuyButton(
            user_id,
            bool(state and state["paid"])
        )
        buy.row=1
        self.add_item(
            buy
        )

class Confirm(discord.ui.View):
    def __init__(
        self,
        user_id,
        message
    ):
        super().__init__(
            timeout=60
        )

        self.user_id=user_id
        self.message=message

    @discord.ui.button(
        emoji="✅",
        style=discord.ButtonStyle.success
    )
    @discord.ui.button(
        emoji="✅",
        style=discord.ButtonStyle.success
    )
    async def yes(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        if it.user.id!=self.user_id:
            await it.response.send_message(
                "not ur season",
                ephemeral=True
            )
            return

        result=seasonal.buy(
            it.guild.id,
            self.user_id
        )

        if not result["ok"]:
            text=(
                f"need "
                f"{result.get('need',0)} "
                f"more 💍"
                if result["reason"]=="rings"
                else "already unlocked"
            )

            await it.response.edit_message(
                content=text,
                view=None
            )
            return

        await it.response.edit_message(
            content=(
                "paid track unlocked "
                "⊹ -3 💍"
            ),
            view=None
        )

        try:
            locked=(
                seasonal.current()
                is None
            )

            file=seasoncardfile(
                self.user_id,
                0,
                locked
            )

            await self.message.edit(
                embeds=[],
                attachments=[
                    file
                ],
                view=(
                    PreviewView(
                        self.user_id,
                        0
                    )
                    if locked
                    else SeasonView(
                        self.user_id,
                        0
                    )
                )
            )

        except discord.HTTPException:
            pass




    @discord.ui.button(
        emoji="❌",
        style=discord.ButtonStyle.secondary
    )
    async def no(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        await it.response.edit_message(
            content="kept ur rings",
            view=None
        )

class SeasonView(discord.ui.View):
    def __init__(
        self,
        user_id,
        page=0
    ):
        super().__init__(
            timeout=None
        )

        self.user_id=user_id

        state=seasonal.state(
            user_id
        )

        if state is None:
            return

        for move in (
            "first",
            "prev",
            "next",
            "last"
        ):
            self.add_item(
                SeasonPageButton(
                    user_id,
                    page,
                    move,
                    False
                )
            )

        helpbutton=HelpButton()
        helpbutton.row=0
        self.add_item(
            helpbutton
        )

        claim=ClaimButton(
            user_id
        )
        claim.row=1
        self.add_item(
            claim
        )

        buy=BuyButton(
            user_id,
            state["paid"]
        )
        buy.row=1
        self.add_item(
            buy
        )

        refresh=RefreshButton(
            user_id
        )
        refresh.row=1
        self.add_item(
            refresh
        )

        if state[
            "season"
        ][
            "halloween"
        ]:
            adventure=AdventureButton(
                user_id
            )
            adventure.row=1
            self.add_item(
                adventure
            )

            brews=BrewsButton(
                user_id
            )
            brews.row=1
            self.add_item(
                brews
            )

class ClaimButton(discord.ui.Button):
    def __init__(
        self,
        user_id
    ):
        super().__init__(
            emoji="🎁",
            style=discord.ButtonStyle.success
        )

        self.user_id=user_id

    async def callback(
        self,
        it:discord.Interaction
    ):
        result=seasonal.claim(
            it.guild.id,
            self.user_id
        )

        if not result["ok"]:
            await it.response.send_message(
                "season isnt open",
                ephemeral=True
            )
            return

        if not result["count"]:
            await it.response.send_message(
                "nothing to claim rn",
                ephemeral=True
            )
            return

        await it.response.defer()

        file=seasoncardfile(
            self.user_id,
            0,
            False
        )

        await it.edit_original_response(
            embeds=[],
            attachments=[
                file
            ],
            view=SeasonView(
                self.user_id,
                0
            )
        )




class BuyButton(discord.ui.Button):
    def __init__(
        self,
        user_id,
        paid=False
    ):
        super().__init__(
            emoji="💍",
            style=(
                discord.ButtonStyle.success
                if paid
                else discord.ButtonStyle.danger
            ),
            disabled=paid
        )

        self.user_id=user_id

    async def callback(
        self,
        it:discord.Interaction
    ):
        await it.response.send_message(
            "unlock paid track for 3 rings?",
            view=Confirm(
                self.user_id,
                it.message
            ),
            ephemeral=True
        )

class RefreshButton(discord.ui.Button):
    def __init__(
        self,
        user_id
    ):
        super().__init__(
            emoji="🔄",
            style=discord.ButtonStyle.secondary
        )

        self.user_id=user_id

    async def callback(
        self,
        it:discord.Interaction
    ):
        await it.response.defer()

        file=seasoncardfile(
            self.user_id,
            0,
            False
        )

        await it.edit_original_response(
            embeds=[],
            attachments=[
                file
            ],
            view=SeasonView(
                self.user_id,
                0
            )
        )




SEASON_ASSETS=(
    Path(
        __file__
    ).resolve().parents[
        1
    ]/
    "assets"/
    "season"
)

SEASON_WITCH_IMAGE=(
    SEASON_ASSETS/
    "witchinghour.png"
)





SEASON_EMBLEM_IMAGE=(
    SEASON_ASSETS/
    "emblem.png"
)
SEASON_EMOJI_DIR=(
    SEASON_ASSETS/
    "emoji"
)




def _season_font(
    size,
    bold=False
):
    paths=(
        (
            "/usr/share/fonts/truetype/dejavu/"
            "DejaVuSerif-Bold.ttf"
        ),
        (
            "/usr/share/fonts/truetype/liberation2/"
            "LiberationSerif-Bold.ttf"
        )
    ) if bold else (
        (
            "/usr/share/fonts/truetype/dejavu/"
            "DejaVuSerif.ttf"
        ),
        (
            "/usr/share/fonts/truetype/liberation2/"
            "LiberationSerif-Regular.ttf"
        )
    )

    for path in paths:
        if Path(
            path
        ).exists():
            return ImageFont.truetype(
                path,
                size
            )

    return ImageFont.load_default()



def _season_image_text(
    value
):
    value=str(
        value
        or ""
    )

    value=re.sub(
        r"<a?:[^:>]+:\d+>",
        "",
        value
    )

    value=(
        value
        .replace(
            "**",
            ""
        )
        .replace(
            "__",
            ""
        )
        .replace(
            "`",
            ""
        )
        .replace(
            "\ufe0f",
            ""
        )
    )

    emojis=(
        rosieemoji.ROSE,
        "🎃",
        "🔒",
        "🔓",
        "💍",
        "🎀",
        "💙",
        "💜",
        "🎨",
        "🎁",
        "🧪"
    )

    for emoji in emojis:
        value=value.replace(
            emoji,
            f" {emoji} "
        )

    return " ".join(
        value.split()
    ).strip(
        " •·"
    )



def _season_field_lines(
    value
):
    rows=[]

    for line in str(
        value
        or ""
    ).splitlines():
        line=_season_image_text(
            line
        )

        if (
            not line
            or line in {
                "•",
                "·"
            }
        ):
            continue

        rows.append(
            line
        )

    return rows


def _season_reward_columns(
    embed
):
    fields=list(
        embed.fields
    )

    columns=[]
    index=0

    while index<len(
        fields
    ):
        field=fields[
            index
        ]

        name=_season_image_text(
            field.name
        ).lstrip(
            "•"
        ).strip()

        free=_season_field_lines(
            field.value
        )

        paid=[]

        if index+1<len(
            fields
        ):
            candidate=fields[
                index+1
            ]

            if (
                str(
                    candidate.name
                    or ""
                )
                .strip()
                .casefold()
                =="paid"
            ):
                paid=_season_field_lines(
                    candidate.value
                )

                index+=1

        if name or free or paid:
            columns.append(
                (
                    name,
                    free,
                    paid
                )
            )

        index+=1

    return columns[
        :3
    ]


def _season_wrap(
    draw,
    text,
    font,
    width
):
    words=str(
        text
    ).split()

    if not words:
        return []

    rows=[]
    current=words[
        0
    ]

    for word in words[
        1:
    ]:
        test=(
            current
            +" "
            +word
        )

        box=draw.textbbox(
            (
                0,
                0
            ),
            test,
            font=font
        )

        if (
            box[
                2
            ]
            -box[
                0
            ]
            <=width
        ):
            current=test

        else:
            rows.append(
                current
            )

            current=word

    rows.append(
        current
    )

    return rows


def _season_draw_reward(
    draw,
    rows,
    x,
    y,
    width
):
    bold=_season_font(
        42,
        True
    )

    regular=_season_font(
        33,
        False
    )

    cursor=y

    for index,text in enumerate(
        rows
    ):
        font=(
            bold
            if index==0
            else regular
        )

        wrapped=_season_wrap(
            draw,
            text,
            font,
            width
        )

        for line in wrapped:
            draw.text(
                (
                    x,
                    cursor
                ),
                line,
                font=font,
                fill=(
                    42,
                    43,
                    49,
                    255
                )
            )

            cursor+=(
                54
                if index==0
                else 45
            )

    return cursor


def _season_emoji_path(
    value
):
    names={
        rosieemoji.ROSE:"rose.png",
        "🎃":"pumpkin.png",
        "🔒":"lock.png",
        "🔓":"unlock.png",
        "💍":"ring.png",
        "🎀":"ribbon.png",
        "💙":"blueheart.png",
        "💜":"purpleheart.png",
        "🎨":"art.png",
        "🎁":"gift.png",
        "🧪":"testtube.png"
    }

    name=names.get(
        value
    )

    if name is None:
        return None

    path=(
        SEASON_EMOJI_DIR/
        name
    )

    return (
        path
        if path.exists()
        else None
    )


def _season_word_width(
    draw,
    word,
    font,
    emoji_size
):
    if _season_emoji_path(
        word
    ) is not None:
        return emoji_size

    box=draw.textbbox(
        (
            0,
            0
        ),
        word,
        font=font
    )

    return (
        box[
            2
        ]
        -box[
            0
        ]
    )


def _season_wrap_rich(
    draw,
    text,
    font,
    width,
    emoji_size
):
    words=str(
        text
    ).split()

    if not words:
        return []

    rows=[]
    current=[]
    current_width=0

    space=_season_word_width(
        draw,
        " ",
        font,
        emoji_size
    )

    for word in words:
        word_width=_season_word_width(
            draw,
            word,
            font,
            emoji_size
        )

        extra=(
            word_width
            if not current
            else space+word_width
        )

        if (
            current
            and current_width+extra>width
        ):
            rows.append(
                current
            )

            current=[
                word
            ]

            current_width=word_width

        else:
            current.append(
                word
            )

            current_width+=extra

    if current:
        rows.append(
            current
        )

    return rows


def _season_draw_rich_line(
    image,
    draw,
    words,
    x,
    y,
    font,
    emoji_size
):
    cursor=x

    space=_season_word_width(
        draw,
        " ",
        font,
        emoji_size
    )

    for index,word in enumerate(
        words
    ):
        if index:
            cursor+=space

        path=_season_emoji_path(
            word
        )

        if path is not None:
            emoji=Image.open(
                path
            ).convert(
                "RGBA"
            )

            emoji=emoji.resize(
                (
                    emoji_size,
                    emoji_size
                ),
                Image.Resampling.LANCZOS
            )

            image.alpha_composite(
                emoji,
                (
                    round(
                        cursor
                    ),
                    round(
                        y-3
                    )
                )
            )

            cursor+=emoji_size

        else:
            draw.text(
                (
                    cursor,
                    y
                ),
                word,
                font=font,
                fill=(
                    42,
                    43,
                    49,
                    255
                )
            )

            cursor+=_season_word_width(
                draw,
                word,
                font,
                emoji_size
            )

    return cursor


def _season_draw_rich(
    image,
    draw,
    text,
    x,
    y,
    width,
    font,
    emoji_size,
    line_height
):
    rows=_season_wrap_rich(
        draw,
        text,
        font,
        width,
        emoji_size
    )

    cursor=y

    for words in rows:
        _season_draw_rich_line(
            image,
            draw,
            words,
            x,
            cursor,
            font,
            emoji_size
        )

        cursor+=line_height

    return cursor


def _season_reward_columns_for_page(
    user_id,
    page
):
    columns=[]

    for old_page in (
        int(
            page
        )*2,
        int(
            page
        )*2+1
    ):
        try:
            embed=_seasonmainembed(
                user_id,
                old_page
            )

            found=_season_reward_columns(
                embed
            )

        except Exception:
            found=[]

        columns.extend(
            found
        )

    return columns[
        :6
    ]


def _season_display_page_count(
    user_id
):
    signatures=[]

    for old_page in range(
        20
    ):
        try:
            columns=_season_reward_columns(
                _seasonmainembed(
                    user_id,
                    old_page
                )
            )

        except Exception:
            break

        if not columns:
            break

        signature=tuple(
            (
                name,
                tuple(
                    free
                ),
                tuple(
                    paid
                )
            )
            for name,free,paid
            in columns
        )

        if signature in signatures:
            break

        signatures.append(
            signature
        )

    old_pages=max(
        1,
        len(
            signatures
        )
    )

    return max(
        1,
        (
            old_pages+1
        )//2
    )


class SeasonDisplayPageButton(
    discord.ui.Button
):
    def __init__(
        self,
        user_id,
        page,
        move
    ):
        emojis={
            "first":"⏮️",
            "prev":"◀️",
            "next":"▶️",
            "last":"⏭️"
        }

        pages=_season_display_page_count(
            user_id
        )

        disabled=(
            (
                move in {
                    "first",
                    "prev"
                }
                and page<=0
            )
            or (
                move in {
                    "next",
                    "last"
                }
                and page>=pages-1
            )
        )

        super().__init__(
            emoji=emojis[
                move
            ],
            style=discord.ButtonStyle.secondary,
            disabled=disabled
        )

        self.user_id=int(
            user_id
        )

        self.page=int(
            page
        )

        self.move=move

    async def callback(
        self,
        it:discord.Interaction
    ):
        pages=_season_display_page_count(
            self.user_id
        )

        if self.move=="first":
            page=0

        elif self.move=="prev":
            page=max(
                0,
                self.page-1
            )

        elif self.move=="next":
            page=min(
                pages-1,
                self.page+1
            )

        else:
            page=max(
                0,
                pages-1
            )

        await it.response.edit_message(
            attachments=seasonfiles(
                self.user_id,
                page
            ),
            view=SeasonLayout(
                self.user_id,
                page
            )
        )


def _season_grid_image(
    user_id,
    page=0
):
    width=1800
    height=710

    image=Image.new(
        "RGBA",
        (
            width,
            height
        ),
        (
            0,
            0,
            0,
            0
        )
    )

    draw=ImageDraw.Draw(
        image
    )

    columns=_season_reward_columns_for_page(
        user_id,
        page
    )

    tierfont=_season_font(
        43,
        True
    )

    amountfont=_season_font(
        35,
        True
    )

    bodyfont=_season_font(
        31,
        False
    )

    paidfont=_season_font(
        31,
        True
    )

    x_positions=(
        42,
        445,
        848
    )

    y_positions=(
        28,
        365
    )

    cell_width=350

    for index,column in enumerate(
        columns
    ):
        name,free,paid=column

        column_index=(
            index%3
        )

        row_index=(
            index//3
        )

        x=x_positions[
            column_index
        ]

        y=y_positions[
            row_index
        ]

        draw.text(
            (
                x,
                y
            ),
            str(
                name
            ),
            font=tierfont,
            fill=(
                42,
                43,
                49,
                255
            )
        )

        cursor=y+62

        for line_index,line in enumerate(
            free
        ):
            font=(
                amountfont
                if line_index==0
                else bodyfont
            )

            cursor=_season_draw_rich(
                image,
                draw,
                line,
                x,
                cursor,
                cell_width,
                font,
                35,
                46
            )

        paid_y=y+190

        if paid:
            draw.text(
                (
                    x,
                    paid_y
                ),
                "paid",
                font=paidfont,
                fill=(
                    42,
                    43,
                    49,
                    255
                )
            )

            cursor=paid_y+46

            for line_index,line in enumerate(
                paid
            ):
                font=(
                    amountfont
                    if line_index==0
                    else bodyfont
                )

                cursor=_season_draw_rich(
                    image,
                    draw,
                    line,
                    x,
                    cursor,
                    cell_width,
                    font,
                    35,
                    46
                )

    emblem=Image.open(
        SEASON_EMBLEM_IMAGE
    ).convert(
        "RGBA"
    )

    box=emblem.getchannel(
        "A"
    ).getbbox()

    if box:
        emblem=emblem.crop(
            box
        )

    max_width=250
    max_height=520

    scale=min(
        max_width/
        emblem.width,
        max_height/
        emblem.height
    )

    target_width=max(
        1,
        round(
            emblem.width
            *scale
        )
    )

    target_height=max(
        1,
        round(
            emblem.height
            *scale
        )
    )

    emblem=emblem.resize(
        (
            target_width,
            target_height
        ),
        Image.Resampling.LANCZOS
    )

    emblem_x=(
        1440
        +(
            285
            -target_width
        )//2
    )

    emblem_y=(
        height
        -target_height
    )//2

    image.alpha_composite(
        emblem,
        (
            emblem_x,
            emblem_y
        )
    )

    return image



def _season_grid_file(
    user_id,
    page=0
):
    image=_season_grid_image(
        user_id,
        page
    )

    buffer=io.BytesIO()

    image.save(
        buffer,
        format="PNG",
        optimize=True
    )

    buffer.seek(
        0
    )

    return discord.File(
        buffer,
        filename="season-grid.png"
    )



def seasonfiles(
    user_id,
    page=0
):
    return [
        discord.File(
            str(
                SEASON_WITCH_IMAGE
            ),
            filename="witchinghour.png"
        ),
        _season_grid_file(
            user_id,
            page
        )
    ]






def _season_native_asset(path,filename):
    image=Image.open(
        path
    ).convert(
        "RGBA"
    )

    box=image.getchannel(
        "A"
    ).getbbox()

    if box:
        image=image.crop(
            box
        )

    buffer=io.BytesIO()

    image.save(
        buffer,
        format="PNG",
        optimize=True
    )

    buffer.seek(
        0
    )

    return discord.File(
        buffer,
        filename=filename
    )


def seasonlayoutfiles():
    return [
        discord.File(
            str(SEASON_WITCH_IMAGE),
            filename="season-witch.png"
        ),
        discord.File(
            str(SEASON_EMBLEM_IMAGE),
            filename="season-emblem.png"
        )
    ]



def _season_visible_width(text):
    text=re.sub(
        r"[*_`~]",
        "",
        str(
            text
        )
    )

    text=text.replace(
        "\ufe0f",
        ""
    )

    return len(
        text
    )


def _season_native_row(values,width=20):
    cells=[]

    for value in values:
        value=str(
            value
            or ""
        )

        if value.strip()=="​":
            value=""

        pad=max(
            2,
            width-_season_visible_width(
                value
            )
        )

        cells.append(
            value
            +"\u2007"*pad
        )

    return "".join(
        cells
    ).rstrip(
        "\u2007"
    )


def _season_reward_text(embed):
    fields=list(
        embed.fields
    )[:3]

    columns=[]

    for field in fields:
        lines=str(
            field.value
        ).splitlines()

        while len(
            lines
        )<7:
            lines.append(
                "​"
            )

        columns.append(
            (
                f"**{field.name}**",
                lines[0],
                lines[1],
                "**paid**",
                lines[4],
                lines[5],
                lines[6]
            )
        )

    while len(
        columns
    )<3:
        columns.append(
            (
                "",
                "",
                "",
                "",
                "",
                "",
                ""
            )
        )

    rows=[]

    for index in range(
        3
    ):
        rows.append(
            _season_native_row(
                [
                    column[index]
                    for column in columns
                ]
            )
        )

    rows.append(
        ""
    )

    for index in range(
        3,
        7
    ):
        rows.append(
            _season_native_row(
                [
                    column[index]
                    for column in columns
                ]
            )
        )

    return "\n".join(
        rows
    ).rstrip()


def _season_emblem_file():
    emblem=Image.open(
        SEASON_EMBLEM_IMAGE
    ).convert(
        "RGBA"
    )

    box=emblem.getchannel(
        "A"
    ).getbbox()

    if box:
        left,top,right,bottom=box
        width=right-left
        height=bottom-top
        size=min(
            width,
            height
        )

        emblem=emblem.crop(
            (
                left,
                top,
                left+size,
                top+size
            )
        )

    buffer=io.BytesIO()

    emblem.save(
        buffer,
        format="PNG",
        optimize=True
    )

    buffer.seek(
        0
    )

    return discord.File(
        buffer,
        filename="emblem.png"
    )


def seasonclassicfiles():
    return [
        discord.File(
            str(
                SEASON_WITCH_IMAGE
            ),
            filename="witchinghour.png"
        ),
        _season_emblem_file()
    ]


def seasonembeds(
    user_id,
    page=0
):
    source=mainembed(
        user_id,
        page
    )

    header=discord.Embed(
        title=source.title,
        description=source.description,
        color=source.color
    )

    header.set_thumbnail(
        url="attachment://witchinghour.png"
    )

    rewards=discord.Embed(
        color=source.color
    )

    for field in source.fields:
        rewards.add_field(
            name=field.name,
            value=field.value,
            inline=True
        )

    rewards.set_thumbnail(
        url="attachment://emblem.png"
    )

    return [
        header,
        rewards
    ]


def seasonnativefiles():
    return [
        discord.File(
            str(
                SEASON_ASSETS/
                "witch-display.png"
            ),
            filename="witch-display.png"
        ),
        discord.File(
            str(
                SEASON_EMBLEM_IMAGE
            ),
            filename="emblem.png"
        )
    ]


def seasonnativeembeds(
    user_id,
    page=0
):
    source=mainembed(
        user_id,
        page
    )

    width="⠀"*80

    header=discord.Embed(
        title=source.title,
        description=source.description,
        color=source.color
    )

    header.set_thumbnail(
        url="attachment://witch-display.png"
    )

    header.set_footer(
        text=width
    )

    rewards=discord.Embed(
        color=source.color
    )

    for field in source.fields[:3]:
        rewards.add_field(
            name=field.name,
            value=field.value,
            inline=True
        )

    rewards.set_thumbnail(
        url="attachment://emblem.png"
    )

    rewards.set_footer(
        text=width
    )

    return [
        header,
        rewards
    ]


def _seasonmainembed(
    user_id,
    page=0
):
    parameters=inspect.signature(
        mainembed
    ).parameters

    if len(
        parameters
    )>=2:
        return mainembed(
            user_id,
            page
        )

    return mainembed(
        user_id
    )


def _seasonlayouttext(
    embed
):
    top=[]

    if embed.title:
        top.append(
            f"## {embed.title}"
        )

    if embed.description:
        top.append(
            str(
                embed.description
            )
        )

    if not top:
        top.append(
            "## 🌙 witching hour"
        )

    return "\n".join(
        top
    )




def _seasonviewpage(
    view,
    fallback=0
):
    value=getattr(
        view,
        "page",
        None
    )

    if value is not None:
        try:
            return int(
                value
            )

        except Exception:
            pass

    for item in getattr(
        view,
        "children",
        ()
    ):
        value=getattr(
            item,
            "page",
            None
        )

        if value is None:
            continue

        try:
            return int(
                value
            )

        except Exception:
            pass

    return int(
        fallback
    )


class _SeasonResponse:
    def __init__(
        self,
        interaction,
        user_id,
        page
    ):
        self.interaction=interaction
        self.response=interaction.response

        self.user_id=int(
            user_id
        )

        self.page=int(
            page
        )

    async def edit_message(
        self,
        **kwargs
    ):
        legacy=kwargs.get(
            "view"
        )

        if isinstance(
            legacy,
            SeasonView
        ):
            user_id=int(
                getattr(
                    legacy,
                    "user_id",
                    self.user_id
                )
            )

            page=_seasonviewpage(
                legacy,
                self.page
            )

            return await self.response.edit_message(
                attachments=seasonfiles(
                    user_id,
                    page
                ),
                view=SeasonLayout(
                    user_id,
                    page
                )
            )

        if (
            "embed" in kwargs
            or "embeds" in kwargs
            or isinstance(
                legacy,
                discord.ui.View
            )
        ):
            kwargs.pop(
                "attachments",
                None
            )

            kwargs[
                "ephemeral"
            ]=True

            return await self.response.send_message(
                **kwargs
            )

        return await self.response.edit_message(
            **kwargs
        )


    def __getattr__(
        self,
        name
    ):
        return getattr(
            self.response,
            name
        )


class _SeasonInteraction:
    def __init__(
        self,
        interaction,
        user_id,
        page
    ):
        self.interaction=interaction

        self.user_id=int(
            user_id
        )

        self.page=int(
            page
        )

        self.response=_SeasonResponse(
            interaction,
            user_id,
            page
        )

    async def edit_original_response(
        self,
        **kwargs
    ):
        legacy=kwargs.get(
            "view"
        )

        if isinstance(
            legacy,
            SeasonView
        ):
            user_id=int(
                getattr(
                    legacy,
                    "user_id",
                    self.user_id
                )
            )

            page=_seasonviewpage(
                legacy,
                self.page
            )

            return await self.interaction.edit_original_response(
                attachments=seasonfiles(
                    user_id,
                    page
                ),
                view=SeasonLayout(
                    user_id,
                    page
                )
            )

        if (
            "embed" in kwargs
            or "embeds" in kwargs
            or isinstance(
                legacy,
                discord.ui.View
            )
        ):
            kwargs.pop(
                "attachments",
                None
            )

            kwargs[
                "ephemeral"
            ]=True

            return await self.interaction.followup.send(
                **kwargs
            )

        return await self.interaction.edit_original_response(
            **kwargs
        )


    def __getattr__(
        self,
        name
    ):
        return getattr(
            self.interaction,
            name
        )


class SeasonLayout(
    discord.ui.LayoutView
):
    def __init__(
        self,
        user_id,
        page=0
    ):
        super().__init__(
            timeout=180
        )

        self.user_id=int(
            user_id
        )

        self.page=max(
            0,
            min(
                3,
                int(
                    page
                )
            )
        )

        embed=_seasonmainembed(
            self.user_id,
            self.page
        )

        container=discord.ui.Container(
            discord.ui.Section(
                discord.ui.TextDisplay(
                    _seasonlayouttext(
                        embed
                    )
                ),
                accessory=discord.ui.Thumbnail(
                    "attachment://season-witch.png",
                    description="witching hour"
                )
            ),
            discord.ui.Separator(),
            discord.ui.Section(
                discord.ui.TextDisplay(
                    _season_reward_text(
                        embed
                    )
                ),
                accessory=discord.ui.Thumbnail(
                    "attachment://season-emblem.png",
                    description="season emblem"
                )
            ),
            accent_color=discord.Color.dark_red()
        )

        self.add_item(
            container
        )

        legacy=SeasonView(
            self.user_id,
            self.page
        )

        rows={}

        for original in legacy.children:
            if not isinstance(
                original,
                discord.ui.Button
            ):
                continue

            row=(
                int(
                    original.row
                )
                if original.row is not None
                else 0
            )

            action=rows.setdefault(
                row,
                discord.ui.ActionRow()
            )

            button=discord.ui.Button(
                label=original.label,
                emoji=original.emoji,
                style=original.style,
                disabled=original.disabled
            )

            callback=original.callback

            async def wrapped(
                it,
                callback=callback
            ):
                return await callback(
                    it
                )

            button.callback=wrapped

            action.add_item(
                button
            )

        for row in sorted(
            rows
        ):
            self.add_item(
                rows[
                    row
                ]
            )

    async def interaction_check(
        self,
        it:discord.Interaction
    ):
        if (
            it.user.id
            !=self.user_id
        ):
            await it.response.send_message(
                "nuh uh",
                ephemeral=True
            )

            return False

        return True



_SEASON_CARD_FONTS={}
_SEASON_CARD_BG=(255,250,245)
_SEASON_CARD_TEXT=(48,39,40)
_SEASON_CARD_RED=(126,31,45)

_witch=_season_card_crop(
    SEASON_WITCH_IMAGE
) if "_season_card_crop" in globals() else None

def _season_card_font(
    size,
    bold=False,
    italic=False
):
    key=(
        int(size),
        bool(bold),
        bool(italic)
    )

    cached=_SEASON_CARD_FONTS.get(
        key
    )

    if cached is not None:
        return cached

    if bold and italic:
        names=(
            "/usr/share/texmf/fonts/opentype/public/tex-gyre/texgyrepagella-bolditalic.otf",
            "/usr/share/fonts/opentype/libertinus/LibertinusSerif-BoldItalic.otf",
            "/usr/share/fonts/opentype/urw-base35/NimbusRoman-BoldItalic.otf",
            "/usr/share/fonts/truetype/liberation2/LiberationSerif-BoldItalic.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-BoldItalic.ttf"
        )

    elif bold:
        names=(
            "/usr/share/texmf/fonts/opentype/public/tex-gyre/texgyrepagella-bold.otf",
            "/usr/share/fonts/opentype/libertinus/LibertinusSerif-Semibold.otf",
            "/usr/share/fonts/opentype/urw-base35/NimbusRoman-Bold.otf",
            "/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
        )

    elif italic:
        names=(
            "/usr/share/texmf/fonts/opentype/public/tex-gyre/texgyrepagella-italic.otf",
            "/usr/share/fonts/opentype/libertinus/LibertinusSerif-Italic.otf",
            "/usr/share/fonts/opentype/urw-base35/NimbusRoman-Italic.otf",
            "/usr/share/fonts/truetype/liberation2/LiberationSerif-Italic.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf"
        )

    else:
        names=(
            "/usr/share/texmf/fonts/opentype/public/tex-gyre/texgyrepagella-regular.otf",
            "/usr/share/fonts/opentype/libertinus/LibertinusSerif-Regular.otf",
            "/usr/share/fonts/opentype/urw-base35/NimbusRoman-Regular.otf",
            "/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
        )

    result=None

    for name in names:
        if Path(
            name
        ).exists():
            result=ImageFont.truetype(
                name,
                int(size)
            )
            break

    if result is None:
        result=ImageFont.load_default()

    _SEASON_CARD_FONTS[
        key
    ]=result

    return result



def _season_card_crop(
    path
):
    image=Image.open(
        path
    ).convert(
        "RGBA"
    )

    box=image.getchannel(
        "A"
    ).getbbox()

    if box:
        image=image.crop(
            box
        )

    return image


def _season_card_width(
    image,
    width
):
    height=max(
        1,
        round(
            image.height
            *width
            /image.width
        )
    )

    return image.resize(
        (
            int(width),
            height
        ),
        Image.Resampling.LANCZOS
    )


def _season_card_moon(
    draw,
    x,
    y,
    size
):
    gold=(
        255,
        211,
        105
    )

    bg=(
        255,
        255,
        255
    )

    draw.ellipse(
        (
            x,
            y,
            x+size,
            y+size
        ),
        fill=gold
    )

    draw.ellipse(
        (
            x+size*.34,
            y-size*.12,
            x+size*1.08,
            y+size*.72
        ),
        fill=bg
    )


def _season_card_icon(
    draw,
    kind,
    x,
    y,
    size=26
):
    x=int(x)
    y=int(y)
    size=int(size)

    gold=(
        217,
        170,
        78
    )

    burgundy=(
        126,
        31,
        45
    )

    muted=(
        125,
        101,
        81
    )

    if kind=="rose":
        cx=x+size*.48
        cy=y+size*.33
        r=size*.18

        for dx,dy in (
            (-.18,0),
            (.18,0),
            (0,-.18),
            (0,.18)
        ):
            draw.ellipse(
                (
                    cx-r+dx*size,
                    cy-r+dy*size,
                    cx+r+dx*size,
                    cy+r+dy*size
                ),
                outline=burgundy,
                width=max(
                    2,
                    size//11
                )
            )

        draw.ellipse(
            (
                cx-r,
                cy-r,
                cx+r,
                cy+r
            ),
            fill=burgundy
        )

        draw.line(
            (
                cx,
                y+size*.52,
                cx,
                y+size*.98
            ),
            fill=gold,
            width=max(
                2,
                size//12
            )
        )

        draw.arc(
            (
                cx-size*.28,
                y+size*.60,
                cx,
                y+size*.84
            ),
            190,
            345,
            fill=gold,
            width=2
        )

    elif kind=="pumpkin":
        draw.ellipse(
            (
                x+size*.10,
                y+size*.22,
                x+size*.90,
                y+size*.88
            ),
            outline=gold,
            width=max(
                2,
                size//10
            )
        )

        draw.arc(
            (
                x+size*.28,
                y+size*.22,
                x+size*.72,
                y+size*.88
            ),
            75,
            285,
            fill=gold,
            width=2
        )

        draw.line(
            (
                x+size*.49,
                y+size*.06,
                x+size*.55,
                y+size*.24
            ),
            fill=burgundy,
            width=max(
                2,
                size//11
            )
        )

    elif kind=="lock":
        draw.arc(
            (
                x+size*.22,
                y+size*.03,
                x+size*.78,
                y+size*.60
            ),
            180,
            360,
            fill=gold,
            width=max(
                2,
                size//9
            )
        )

        draw.rounded_rectangle(
            (
                x+size*.12,
                y+size*.37,
                x+size*.88,
                y+size*.96
            ),
            radius=max(
                2,
                size//10
            ),
            outline=gold,
            width=max(
                2,
                size//10
            )
        )

        draw.ellipse(
            (
                x+size*.44,
                y+size*.58,
                x+size*.56,
                y+size*.70
            ),
            fill=burgundy
        )

    elif kind=="ring":
        draw.ellipse(
            (
                x+size*.23,
                y+size*.35,
                x+size*.77,
                y+size*.92
            ),
            outline=gold,
            width=max(
                2,
                size//9
            )
        )

        draw.polygon(
            (
                (
                    x+size*.50,
                    y
                ),
                (
                    x+size*.68,
                    y+size*.20
                ),
                (
                    x+size*.50,
                    y+size*.35
                ),
                (
                    x+size*.32,
                    y+size*.20
                )
            ),
            fill=burgundy
        )

    elif kind=="candle":
        draw.rectangle(
            (
                x+size*.34,
                y+size*.38,
                x+size*.66,
                y+size*.94
            ),
            outline=gold,
            width=2
        )

        draw.polygon(
            (
                (
                    x+size*.50,
                    y
                ),
                (
                    x+size*.37,
                    y+size*.29
                ),
                (
                    x+size*.50,
                    y+size*.40
                ),
                (
                    x+size*.63,
                    y+size*.29
                )
            ),
            fill=burgundy
        )

    elif kind=="bone":
        draw.line(
            (
                x+size*.22,
                y+size*.77,
                x+size*.78,
                y+size*.23
            ),
            fill=gold,
            width=max(
                3,
                size//6
            )
        )

    elif kind=="web":
        cx=x+size*.50
        cy=y+size*.50

        for px,py in (
            (
                x,
                y
            ),
            (
                x+size,
                y
            ),
            (
                x,
                y+size
            ),
            (
                x+size,
                y+size
            )
        ):
            draw.line(
                (
                    cx,
                    cy,
                    px,
                    py
                ),
                fill=muted,
                width=1
            )

        draw.ellipse(
            (
                x+size*.25,
                y+size*.25,
                x+size*.75,
                y+size*.75
            ),
            outline=gold,
            width=1
        )



def _season_card_extra(
    draw,
    value,
    x,
    y
):
    value=str(
        value
    ).strip()

    if (
        not value
        or value=="​"
    ):
        return

    mapping=(
        (
            "🎃",
            "pumpkin"
        ),
        (
            "💍",
            "ring"
        ),
        (
            "🕸️",
            "web"
        ),
        (
            "🕯️",
            "candle"
        ),
        (
            "🦴",
            "bone"
        )
    )

    for emoji,kind in mapping:
        if value.startswith(
            emoji
        ):
            _season_card_icon(
                draw,
                kind,
                x,
                y+1,
                27
            )

            value=value[
                len(
                    emoji
                ):
            ].strip()

            draw.text(
                (
                    x+34,
                    y
                ),
                value,
                font=_season_card_font(
                    23
                ),
                fill=_SEASON_CARD_TEXT
            )

            return

    draw.text(
        (
            x,
            y
        ),
        value,
        font=_season_card_font(
            23
        ),
        fill=_SEASON_CARD_TEXT
    )


def _season_card_status(
    draw,
    marker,
    x,
    y,
    size=26
):
    if marker=="🔒":
        _season_card_icon(
            draw,
            "lock",
            x,
            y,
            size
        )

        return x+size+8

    draw.text(
        (
            x,
            y-3
        ),
        marker,
        font=_season_card_font(
            27,
            True
        ),
        fill=_SEASON_CARD_TEXT
    )

    return x+31


def _season_card_date(
    value
):
    return value.strftime(
        "%B %d, %Y"
    ).replace(
        " 0",
        " "
    )


def _season_card_payload(
    user_id,
    page=0,
    locked=False
):
    current=seasonal.current()

    if current is None:
        data=seasonal.preview()
        state=None
        locked=True
    else:
        data=current
        state=seasonal.state(
            user_id
        )

    page,first,last=pagebounds(
        page
    )

    xp=(
        0
        if state is None
        else int(
            state["xp"]
        )
    )

    rows=[]

    for tier in range(
        first,
        last+1
    ):
        if (
            locked
            or state is None
        ):
            freeicon="🔒"
            paidicon="🔒"

        else:
            freeicon=(
                "✓"
                if (
                    "free",
                    tier
                ) in state["claims"]
                else (
                    "◆"
                    if state["tier"]>=tier
                    else "•"
                )
            )

            paidicon=(
                "✓"
                if (
                    "paid",
                    tier
                ) in state["claims"]
                else (
                    "◆"
                    if (
                        state["paid"]
                        and state["tier"]>=tier
                    )
                    else (
                        "•"
                        if state["paid"]
                        else "🔒"
                    )
                )
            )

        freeextra=seasonextra(
            "free",
            tier,
            data["halloween"]
        )

        paidextra=seasonextra(
            "paid",
            tier,
            data["halloween"]
        )

        paidlines=[]

        if tier in (
            6,
            10
        ):
            paidlines.append(
                "💍 1 ring"
            )

        if paidextra!="​":
            paidlines.append(
                paidextra
            )

        rows.append(
            {
                "tier":tier,
                "freeicon":freeicon,
                "paidicon":paidicon,
                "free":int(
                    seasonal.FREE[
                        tier
                    ]
                ),
                "paid":int(
                    seasonal.PAID[
                        tier
                    ]
                ),
                "freeextra":freeextra,
                "paidlines":paidlines
            }
        )

    return {
        "name":data["name"],
        "number":int(
            data["number"]
        ),
        "start":data["start"],
        "end":
            data["end"]
            -timedelta(
                seconds=1
            ),
        "xp":xp,
        "rows":rows,
        "page":page,
        "locked":locked
    }


def _season_card_title_font(
    size
):
    names=(
        (
            "/usr/share/texmf/fonts/opentype/public/"
            "tex-gyre/texgyrechorus-mediumitalic.otf",
            1.65
        ),
        (
            "/usr/share/fonts/opentype/urw-base35/"
            "Z003-MediumItalic.otf",
            1.65
        ),
        (
            "/usr/share/fonts/truetype/freefont/"
            "FreeSerifItalic.ttf",
            1.0
        ),
        (
            "/usr/share/fonts/truetype/dejavu/"
            "DejaVuSerifCondensed-Italic.ttf",
            1.0
        )
    )

    for name,scale in names:
        if Path(
            name
        ).exists():
            return ImageFont.truetype(
                name,
                round(
                    size*scale
                )
            )

    return _season_card_font(
        size,
        False,
        True
    )



def _season_card_ornament(
    draw,
    x,
    y,
    size=12
):
    gold=(
        217,
        170,
        78
    )

    x=int(x)
    y=int(y)
    size=int(size)

    draw.polygon(
        (
            (
                x,
                y-size
            ),
            (
                x+size*.28,
                y-size*.28
            ),
            (
                x+size,
                y
            ),
            (
                x+size*.28,
                y+size*.28
            ),
            (
                x,
                y+size
            ),
            (
                x-size*.28,
                y+size*.28
            ),
            (
                x-size,
                y
            ),
            (
                x-size*.28,
                y-size*.28
            )
        ),
        fill=gold
    )



def _season_card_stamp_frame(
    draw,
    box
):
    left,top,right,bottom=map(
        int,
        box
    )

    paper=_SEASON_CARD_BG

    stamp=(
        255,
        252,
        245
    )

    gold=(
        217,
        170,
        78
    )

    burgundy=(
        126,
        31,
        45
    )

    draw.rectangle(
        (
            left,
            top,
            right,
            bottom
        ),
        fill=stamp
    )

    radius=8
    step=23

    for x in range(
        left+11,
        right-10,
        step
    ):
        draw.ellipse(
            (
                x-radius,
                top-radius,
                x+radius,
                top+radius
            ),
            fill=paper
        )

        draw.ellipse(
            (
                x-radius,
                bottom-radius,
                x+radius,
                bottom+radius
            ),
            fill=paper
        )

    for y in range(
        top+11,
        bottom-10,
        step
    ):
        draw.ellipse(
            (
                left-radius,
                y-radius,
                left+radius,
                y+radius
            ),
            fill=paper
        )

        draw.ellipse(
            (
                right-radius,
                y-radius,
                right+radius,
                y+radius
            ),
            fill=paper
        )

    draw.rounded_rectangle(
        (
            left+12,
            top+12,
            right-12,
            bottom-12
        ),
        radius=7,
        outline=gold,
        width=3
    )

    draw.rounded_rectangle(
        (
            left+21,
            top+21,
            right-21,
            bottom-21
        ),
        radius=5,
        outline=burgundy,
        width=1
    )

    for x,y in (
        (
            left+28,
            top+28
        ),
        (
            right-28,
            top+28
        ),
        (
            left+28,
            bottom-28
        ),
        (
            right-28,
            bottom-28
        )
    ):
        _season_card_ornament(
            draw,
            x,
            y,
            4
        )


_SEASON_TITLE_STYLE=None

def _season_card_title_style():
    global _SEASON_TITLE_STYLE

    if _SEASON_TITLE_STYLE is not None:
        return _SEASON_TITLE_STYLE

    fraktur="𝔴𝔦𝔱𝔠𝔥𝔦𝔫𝔤 𝔥𝔬𝔲𝔯"

    fonts=(
        "/usr/share/fonts/truetype/noto/NotoSansMath-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuMathTeXGyre.ttf",
        "/usr/share/fonts/opentype/stix-word/STIXMath-Regular.otf"
    )

    for name in fonts:
        if Path(
            name
        ).exists():
            _SEASON_TITLE_STYLE=(
                fraktur,
                ImageFont.truetype(
                    name,
                    100
                )
            )

            return _SEASON_TITLE_STYLE

    _SEASON_TITLE_STYLE=(
        "witching hour",
        _season_card_font(
            68,
            True
        )
    )

    return _SEASON_TITLE_STYLE



def _season_card_postmark(
    image
):
    gold=(
        217,
        170,
        78,
        220
    )

    layer=Image.new(
        "RGBA",
        (
            365,
            135
        ),
        (
            0,
            0,
            0,
            0
        )
    )

    draw=ImageDraw.Draw(
        layer
    )

    draw.ellipse(
        (
            8,
            14,
            114,
            120
        ),
        outline=gold,
        width=3
    )

    for row in range(
        5
    ):
        y=31+row*17

        points=[]

        for x in range(
            74,
            356,
            4
        ):
            phase=(
                x-74
            )%48

            if phase<12:
                offset=-phase*.42

            elif phase<24:
                offset=-5+(phase-12)*.42

            elif phase<36:
                offset=(phase-24)*.42

            else:
                offset=5-(phase-36)*.42

            points.append(
                (
                    x,
                    round(
                        y+offset
                    )
                )
            )

        draw.line(
            points,
            fill=gold,
            width=2
        )

    layer=layer.rotate(
        10,
        resample=Image.Resampling.BICUBIC,
        expand=True
    )

    image.paste(
        layer,
        (
            500,
            140
        ),
        layer
    )





def _season_card_render(
    user_id,
    page=0,
    locked=False
):
    info=_season_card_payload(
        user_id,
        page,
        locked
    )

    width=1200
    height=780

    paper=(
        253,
        249,
        241
    )

    ink=(
        48,
        39,
        40
    )

    burgundy=(
        126,
        31,
        45
    )

    gold=(
        217,
        170,
        78
    )

    muted=(
        137,
        117,
        102
    )

    border=(
        217,
        202,
        181
    )

    image=Image.new(
        "RGB",
        (
            width,
            height
        ),
        paper
    )

    draw=ImageDraw.Draw(
        image
    )

    draw.rounded_rectangle(
        (
            14,
            14,
            width-14,
            height-14
        ),
        radius=12,
        outline=border,
        width=2
    )

    draw.rounded_rectangle(
        (
            26,
            31,
            32,
            height-31
        ),
        radius=3,
        fill=burgundy
    )

    title_text,title_font=_season_card_title_style()

    title_box=draw.textbbox(
        (
            0,
            0
        ),
        title_text,
        font=title_font
    )

    title_height=(
        title_box[3]
        -title_box[1]
    )

    title_x=125
    title_y=38

    moon_size=58

    _season_card_moon(
        draw,
        49,
        title_y
        +(
            title_height
            -moon_size
        )//2,
        moon_size
    )

    draw.text(
        (
            title_x
            -title_box[0],
            title_y
            -title_box[1]
        ),
        title_text,
        font=title_font,
        fill=ink
    )

    subtitle=_season_card_font(
        18,
        True
    )

    subtitle_x=title_x
    subtitle_y=111

    left_text="ROSIE POST"
    right_text="HAPPY HALLOWEEN"

    left_box=draw.textbbox(
        (
            0,
            0
        ),
        left_text,
        font=subtitle
    )

    right_box=draw.textbbox(
        (
            0,
            0
        ),
        right_text,
        font=subtitle
    )

    left_width=(
        left_box[2]
        -left_box[0]
    )

    dot_gap=42

    draw.text(
        (
            subtitle_x
            -left_box[0],
            subtitle_y
            -left_box[1]
        ),
        left_text,
        font=subtitle,
        fill=burgundy
    )

    dotx=(
        subtitle_x
        +left_width
        +dot_gap//2
    )

    doty=(
        subtitle_y
        +(
            left_box[3]
            -left_box[1]
        )//2
    )

    draw.ellipse(
        (
            dotx-4,
            doty-4,
            dotx+4,
            doty+4
        ),
        fill=gold
    )

    draw.text(
        (
            subtitle_x
            +left_width
            +dot_gap
            -right_box[0],
            subtitle_y
            -right_box[1]
        ),
        right_text,
        font=subtitle,
        fill=burgundy
    )

    draw.text(
        (
            57,
            146
        ),
        f"season {info['number']:02d}",
        font=_season_card_font(
            28
        ),
        fill=ink
    )

    label=_season_card_font(
        27
    )

    draw.text(
        (
            57,
            187
        ),
        "start",
        font=label,
        fill=ink
    )

    _season_card_ornament(
        draw,
        154,
        204,
        7
    )

    draw.text(
        (
            178,
            187
        ),
        _season_card_date(
            info["start"]
        ),
        font=label,
        fill=ink
    )

    draw.text(
        (
            57,
            228
        ),
        "end",
        font=label,
        fill=ink
    )

    _season_card_ornament(
        draw,
        154,
        245,
        7
    )

    draw.text(
        (
            178,
            228
        ),
        _season_card_date(
            info["end"]
        ),
        font=label,
        fill=ink
    )

    _season_card_postmark(
        image
    )

    draw.text(
        (
            57,
            289
        ),
        "XP",
        font=_season_card_font(
            30
        ),
        fill=ink
    )

    _season_card_ornament(
        draw,
        115,
        307,
        7
    )

    draw.text(
        (
            140,
            286
        ),
        f"{info['xp']:,} / {seasonal.MAX_XP:,}",
        font=_season_card_font(
            31,
            True
        ),
        fill=ink
    )

    bar_x=57
    bar_y=330
    bar_w=835
    bar_h=31

    draw.rounded_rectangle(
        (
            bar_x,
            bar_y,
            bar_x+bar_w,
            bar_y+bar_h
        ),
        radius=7,
        fill=(
            246,
            240,
            231
        ),
        outline=border,
        width=2
    )

    ratio=max(
        0,
        min(
            1,
            info["xp"]
            /max(
                1,
                seasonal.MAX_XP
            )
        )
    )

    filled=round(
        (
            bar_w-8
        )
        *ratio
    )

    if filled:
        draw.rounded_rectangle(
            (
                bar_x+4,
                bar_y+4,
                bar_x+4+filled,
                bar_y+bar_h-4
            ),
            radius=4,
            fill=burgundy
        )

    stamp=(
        912,
        24,
        1158,
        270
    )

    _season_card_stamp_frame(
        draw,
        stamp
    )

    witch=_SEASON_CARD_WITCH

    stamp_center=(
        stamp[0]
        +stamp[2]
    )//2

    stamp_height=(
        stamp[3]
        -stamp[1]
    )

    image.paste(
        witch,
        (
            stamp_center
            -witch.width//2,
            stamp[1]
            +(
                stamp_height
                -witch.height
            )//2
        ),
        witch
    )

    month="OCTOBER 2026"

    month_font=_season_card_font(
        15,
        True
    )

    month_box=draw.textbbox(
        (
            0,
            0
        ),
        month,
        font=month_font
    )

    month_width=(
        month_box[2]
        -month_box[0]
    )

    month_x=(
        stamp_center
        -month_width//2
    )

    draw.line(
        (
            930,
            281,
            month_x-12,
            281
        ),
        fill=gold,
        width=1
    )

    draw.text(
        (
            month_x,
            271
        ),
        month,
        font=month_font,
        fill=burgundy
    )

    draw.line(
        (
            month_x
            +month_width
            +12,
            281,
            1138,
            281
        ),
        fill=gold,
        width=1
    )

    positions=(
        57,
        345,
        633
    )

    for x,row in zip(
        positions,
        info["rows"]
    ):
        draw.ellipse(
            (
                x,
                409,
                x+9,
                418
            ),
            fill=gold
        )

        draw.text(
            (
                x+21,
                395
            ),
            f"{row['tier']:02d}",
            font=_season_card_font(
                32,
                True
            ),
            fill=ink
        )

        amount=f"{row['free']:,}"

        draw.text(
            (
                x,
                449
            ),
            amount,
            font=_season_card_font(
                32,
                True
            ),
            fill=ink
        )

        amount_box=draw.textbbox(
            (
                0,
                0
            ),
            amount,
            font=_season_card_font(
                32,
                True
            )
        )

        _season_card_icon(
            draw,
            "rose",
            x
            +amount_box[2]
            +13,
            452,
            28
        )

        _season_card_extra(
            draw,
            row["freeextra"],
            x,
            496
        )

        paid_font=_season_card_font(
            30,
            True
        )

        draw.text(
            (
                x,
                567
            ),
            "PAID",
            font=paid_font,
            fill=burgundy
        )

        paid_label_box=draw.textbbox(
            (
                0,
                0
            ),
            "PAID",
            font=paid_font
        )

        draw.line(
            (
                x,
                606,
                x
                +paid_label_box[2]
                -paid_label_box[0],
                606
            ),
            fill=gold,
            width=2
        )

        cursor=_season_card_status(
            draw,
            row["paidicon"],
            x,
            621,
            28
        )

        paid=f"{row['paid']:,}"

        draw.text(
            (
                cursor,
                615
            ),
            paid,
            font=_season_card_font(
                31,
                True
            ),
            fill=ink
        )

        paid_box=draw.textbbox(
            (
                0,
                0
            ),
            paid,
            font=_season_card_font(
                31,
                True
            )
        )

        _season_card_icon(
            draw,
            "rose",
            cursor
            +paid_box[2]
            +11,
            619,
            27
        )

        for index,value in enumerate(
            row["paidlines"][:2]
        ):
            _season_card_extra(
                draw,
                value,
                x,
                662
                +index*34
            )

    emblem=_SEASON_CARD_EMBLEM

    image.paste(
        emblem,
        (
            1039
            -emblem.width//2,
            bar_y-7
        ),
        emblem
    )

    return image





def seasoncardfile(
    user_id,
    page=0,
    locked=False
):
    image=_season_card_render(
        user_id,
        page,
        locked
    )

    buffer=io.BytesIO()

    image.save(
        buffer,
        format="PNG",
        compress_level=1
    )

    buffer.seek(
        0
    )

    return discord.File(
        buffer,
        filename="season-card.png"
    )


def seasoncardembed():
    embed=discord.Embed()

    embed.set_image(
        url="attachment://season-card.png"
    )

    return embed


_SEASON_CARD_WITCH=_season_card_width(
    _season_card_crop(
        SEASON_WITCH_IMAGE
    ),
    205
)


_SEASON_CARD_EMBLEM=_season_card_width(
    _season_card_crop(
        SEASON_EMBLEM_IMAGE
    ),
    205
)


class Seasonal(commands.Cog):
    def __init__(
        self,
        bot
    ):
        self.bot=bot
        self.done=False

    async def registry(self):
        if self.done:
            return

        app_id=(
            self.bot.application_id
            or self.bot.user.id
        )

        rows=await self.bot.http.get_global_commands(
            app_id
        )

        season_found=False

        for row in rows:
            name=row.get(
                "name"
            )

            kind=int(
                row.get(
                    "type",
                    1
                )
            )

            if (
                kind==1
                and name in {
                    "pass",
                    "hallow"
                }
            ):
                route=Route(
                    "DELETE",
                    "/applications/{application_id}/commands/{command_id}",
                    application_id=app_id,
                    command_id=row[
                        "id"
                    ]
                )

                await self.bot.http.request(
                    route
                )

            if (
                kind==1
                and name=="season"
            ):
                season_found=True

                if row.get("description")!="open rosie's season":
                    await self.bot.http.request(
                        Route(
                            "PATCH",
                            "/applications/{application_id}/commands/{command_id}",
                            application_id=app_id,
                            command_id=row["id"]
                        ),
                        json={
                            "description":"open rosie's season"
                        }
                    )

        if not season_found:
            route=Route(
                "POST",
                "/applications/{application_id}/commands",
                application_id=app_id
            )

            await self.bot.http.request(
                route,
                json={
                    "name":"season",
                    "description":"open rosie's season",
                    "type":1
                }
            )

        self.done=True

        print(
            "season command registry ✓"
        )

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            await self.registry()

        except Exception as error:
            print(
                f"season registry failed ⊹ {error}"
            )

    @app_commands.command(
        name="season",
        description="open rosie's season"
    )
    @app_commands.guild_only()
    async def seasoncmd(
        self,
        it:discord.Interaction
    ):
        await it.response.defer(
            thinking=True
        )

        locked=(
            seasonal.current()
            is None
        )

        file=seasoncardfile(
            it.user.id,
            0,
            locked
        )

        await it.edit_original_response(
            embeds=[],
            attachments=[
                file
            ],
            view=(
                PreviewView(
                    it.user.id,
                    0
                )
                if locked
                else SeasonView(
                    it.user.id,
                    0
                )
            )
        )




async def setup(bot):
    await bot.add_cog(
        Seasonal(bot)
    )
