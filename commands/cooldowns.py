import importlib
import time

import discord
from core import brewing
from core import casino
from core import game
from core import petbuff
from core import seasonal
from discord import app_commands
from discord.ext import commands
from core import emoji as rosieemoji

def wait(stamp):
    return (
        "ready"
        if not stamp or stamp<=time.time()
        else f"<t:{int(stamp)}:R>"
    )

def add(lines,command,status):
    lines.append(
        f"`/{command}` ⊹ {status}"
    )

def build(user_id,guild_id):
    now=time.time()
    reset=game.next_reset().timestamp()
    ready=[]
    reminders=[]
    daily=[]
    events=[]
    petlines=[]

    if game.has_daily(user_id):
        add(
            daily,
            "daily",
            f"<t:{int(reset)}:R>"
        )
    else:
        add(daily,"daily","ready")
        ready.append("`/daily`")

    scratch=game.scratch_state(user_id)

    if not game.has_daily(user_id):
        add(
            daily,
            "scratch",
            "grab /daily first"
        )
    elif scratch is None:
        add(daily,"scratch","ready")
        ready.append("`/scratch`")
    elif scratch["finished"]:
        add(
            daily,
            "scratch",
            f"done ⊹ <t:{int(reset)}:R>"
        )
    else:
        left=max(
            0,
            4-len(scratch["revealed"])
        )
        add(
            daily,
            "scratch",
            f"{left} scratch"
            f"{'es' if left!=1 else ''} left"
        )
        ready.append("`/scratch`")

    try:
        quests=importlib.import_module(
            "commands.quests"
        )

        with quests.connect() as con:
            exists=con.execute(
                "SELECT 1 FROM quest_days "
                "WHERE user_id=? AND day=?",
                (
                    user_id,
                    game.day().isoformat()
                )
            ).fetchone()

        if exists:
            data,items=quests.state(user_id)

            done=sum(
                item["done"]
                for item in items
            )

            claimable=sum(
                item["done"]
                and not item["claimed"]
                for item in items
            )

            text=f"{done}/3 done"

            if claimable:
                text+=(
                    f" ⊹ {claimable} claimable"
                )

                reminders.append(
                    f"📜 {claimable} quest reward"
                    f"{'s' if claimable!=1 else ''} waiting"
                )

                ready.append(
                    "`/quests`"
                )

            add(
                daily,
                "quests",
                text+f" ⊹ <t:{int(reset)}:R>"
            )
        else:
            add(
                daily,
                "quests",
                "ready"
            )

            ready.append(
                "`/quests`"
            )
    except Exception:
        pass

    try:
        pluck=importlib.import_module(
            "commands.pluck"
        )

        stats=pluck.stats(user_id)
        count=stats.get("today",0)

        if count>=pluck.LIMIT:
            status=(
                f"{count}/{pluck.LIMIT} ⊹ "
                f"<t:{int(reset)}:R>"
            )
        else:
            stamp=stats.get("ready",0)

            status=(
                f"{count}/{pluck.LIMIT} ⊹ "
                f"{wait(stamp)}"
            )

            if stamp<=now:
                ready.append(
                    "`/pluck`"
                )

        if stats.get("disease")=="rosacea":
            status+=' ⊹ ' + rosieemoji.ROSE + ' rosacea'

        elif stats.get("disease")=="roseola":
            status+=" ⊹ 🥀 roseola • -50%"

        immune=float(stats.get("immune_until",0) or 0)

        if immune>now:
            status+=f" ⊹ 💊 protected <t:{int(immune)}:R>"

        add(
            daily,
            "pluck",
            status
        )
    except Exception:
        pass

    try:
        campaign=importlib.import_module(
            "commands.campaign"
        )

        run=campaign.active(user_id)

        if run:
            add(
                daily,
                "campaign",
                "run active"
            )

            ready.append(
                "`/campaign`"
            )
        else:
            stamp=campaign.ready(user_id)

            add(
                daily,
                "campaign",
                wait(stamp)
            )

            if stamp<=now:
                ready.append(
                    "`/campaign`"
                )
    except Exception:
        pass

    try:
        data=brewing.forage_state(user_id)
        energy=int(data["energy"])
        maximum=int(data.get("max_energy",brewing.MAX_ENERGY))
        nextat=data["next"]
        status=f"energy {energy}/{maximum}"
        status+=(
            " ⊹ full"
            if energy>=maximum
            else f" ⊹ next <t:{int(nextat)}:R>"
        )
        add(daily,"forage",status)
        if energy>0:
            ready.append("`/forage`")
    except Exception:
        pass

    try:
        garden=importlib.import_module(
            "commands.garden"
        )

        u,plants,gday=garden.state(
            user_id
        )

        count=sum(
            row["ready_at"]<=now
            for row in plants
        )

        cap=garden.cap(
            u["xp"]
        )

        if count:
            status=(
                f"{count} ready to harvest"
            )

            reminders.append(
                f'{rosieemoji.ROSE} garden has {count} ready'
            )

            ready.append(
                "`/garden`"
            )

        elif plants:
            stamp=min(
                row["ready_at"]
                for row in plants
            )

            status=(
                f"next harvest "
                f"<t:{int(stamp)}:R>"
            )

        else:
            status="nothing growing"

        status+=(
            f" ⊹ bloom "
            f"{gday['profit']:,}/{cap:,}"
        )

        add(
            daily,
            "garden",
            status
        )
    except Exception:
        pass

    try:
        season=seasonal.current()
        if season:
            if season["halloween"]:
                with seasonal.connect() as con:
                    rows=con.execute(
                        "SELECT key,amount FROM season_daily "
                        "WHERE user_id=? AND season=? AND day=? "
                        "AND key IN ('adventure','ingredient:forage')",
                        (user_id,season["id"],seasonal.today())
                    ).fetchall()
                used={row["key"]:int(row["amount"]) for row in rows}
                done=used.get("adventure",0)>=1
                adventure=(
                    f"done ⊹ <t:{int(reset)}:R>"
                    if done
                    else "ready"
                )
                status=(
                    f"adventure {adventure} ⊹ "
                    f"forage bonuses {min(10,used.get('ingredient:forage',0))}/10"
                )
                if not done:
                    ready.append("`/season` adventure")
            else:
                status=f"ends <t:{int(season['end'].timestamp())}:R>"
            add(daily,"season",status)
    except Exception:
        pass

    try:
        with casino.connect() as con:
            row=con.execute(
                "SELECT wagered "
                "FROM casino_days "
                "WHERE user_id=? AND day=?",
                (
                    user_id,
                    game.day().isoformat()
                )
            ).fetchone()

        wagered=(
            int(row["wagered"])
            if row
            else 0
        )

        remaining=max(
            0,
            casino.CAP-wagered
        )

        add(
            daily,
            "casino",
            f"{remaining:,}/{casino.CAP:,} "
            f"wager room ⊹ "
            f"<t:{int(reset)}:R>"
        )
    except Exception:
        pass

    try:
        pet=importlib.import_module(
            "commands.pet"
        )

        with pet.connect() as con:
            current=pet.active(
                con,
                user_id
            )

        if current:
            info=pet.SPECIES[
                current["species"]
            ]

            petlines.append(
                f"{info['emoji']} "
                f"**{current['name']}** "
                f"⊹ lvl {current['level']}"
            )

            feed=(
                current["last_feed"]
                +pet.FEED_CD
            )

            play=(
                current["last_play"]
                +pet.PLAY_CD
            )

            explore=(
                current["last_explore"]
                +pet.EXPLORE_CD
            )

            play_status=wait(play)
            explore_status=wait(explore)

            if play<=now and current["energy"]<10:
                play_status="need 10 energy"

            if explore<=now and current["energy"]<15:
                explore_status="need 15 energy"

            petlines.append(
                f"feed ⊹ {wait(feed)}"
            )

            petlines.append(
                f"play ⊹ {play_status}"
            )

            petlines.append(
                f"explore ⊹ {explore_status}"
            )

            if feed<=now:
                ready.append(
                    "`/pet` feed"
                )

            if play<=now and current["energy"]>=10:
                ready.append(
                    "`/pet` play"
                )

            if explore<=now and current["energy"]>=15:
                ready.append(
                    "`/pet` explore"
                )
        else:
            petlines.append(
                "no pet yet"
            )
    except Exception:
        petlines.append(
            "pet status unavailable"
        )

    buff=petbuff.get(user_id)

    if buff:
        petlines.append(
            f"{buff['emoji']} "
            f"**{buff['label']}** ⊹ "
            f"{buff['text']} ⊹ "
            f"<t:{int(buff['expires_at'])}:R>"
        )

    try:
        marriage=importlib.import_module(
            "commands.marriage"
        )

        data=marriage.active(
            user_id
        )

        if data:
            stamp=(
                data["last_claim"]
                +marriage.WEEK
            )

            add(
                daily,
                "marriage",
                f"stipend ⊹ {wait(stamp)}"
            )

            if stamp<=now:
                ready.append(
                    "`/marriage` claim"
                )

                reminders.append(
                    "💍 weekly marriage stipend ready"
                )
    except Exception:
        pass

    try:
        sin=importlib.import_module(
            "commands.sin"
        )

        data=sin.active_game(
            guild_id
        )

        if data:
            close=sin.midnight_after(
                data["current_day"]
            )

            with sin.connect() as con:
                choice=con.execute(
                    "SELECT number "
                    "FROM sin_choices "
                    "WHERE game_id=? "
                    "AND day=? "
                    "AND user_id=?",
                    (
                        data["id"],
                        data["current_day"],
                        user_id
                    )
                ).fetchone()

            if choice:
                add(
                    events,
                    "sin",
                    f"entered today ⊹ "
                    f"**#{choice['number']}** "
                    f"⊹ resolves <t:{close}:R>"
                )

            else:
                add(
                    events,
                    "sin",
                    f"‼️ not chosen today ⊹ "
                    f"closes <t:{close}:R>"
                )

                reminders.append(
                    "♦️ sin is live and "
                    "you haven't chosen today"
                )
    except Exception:
        pass

    try:
        boss=importlib.import_module(
            "commands.boss"
        )

        data=boss.active(
            guild_id
        )

        if data:
            with boss.connect() as con:
                player=con.execute(
                    "SELECT last_action "
                    "FROM boss_players "
                    "WHERE game_id=? "
                    "AND user_id=?",
                    (
                        data["id"],
                        user_id
                    )
                ).fetchone()

            stamp=(
                player["last_action"]
                +boss.COOLDOWN
                if player
                else 0
            )

            state=(
                "not joined"
                if player is None
                else wait(stamp)
            )

            add(
                events,
                "boss",
                f"{state} ⊹ ends "
                f"<t:{int(data['ends_at'])}:R>"
            )

            if stamp<=now:
                ready.append(
                    "boss action"
                )
    except Exception:
        pass

    try:
        reaper=importlib.import_module(
            "commands.reaper"
        )

        data=reaper.active_game(
            guild_id
        )

        if data:
            with reaper.connect() as con:
                player=con.execute(
                    "SELECT last_reap_at "
                    "FROM reaper_scores "
                    "WHERE game_id=? "
                    "AND user_id=?",
                    (
                        data["id"],
                        user_id
                    )
                ).fetchone()

            if player is None:
                state="not participated"

            else:
                stamp=(
                    player["last_reap_at"]
                    +data["cooldown"]
                    if player["last_reap_at"]
                    else 0
                )

                state=wait(stamp)

            add(
                events,
                "reaper",
                state
            )

        else:
            add(
                events,
                "reaper",
                "no active event"
            )
    except Exception:
        pass

    try:
        relic=importlib.import_module(
            "commands.relic"
        )

        data=relic.active(
            guild_id
        )

        if data:
            if data["holder_id"]==user_id:
                state="you have it"

            else:
                with relic.connect() as con:
                    player=con.execute(
                        "SELECT last_steal_at "
                        "FROM relic_players "
                        "WHERE game_id=? "
                        "AND user_id=?",
                        (
                            data["id"],
                            user_id
                        )
                    ).fetchone()

                stamps=[]

                if (
                    player
                    and player["last_steal_at"]
                ):
                    stamps.append(
                        player["last_steal_at"]
                        +data["cooldown"]
                    )

                if (
                    data["previous_holder_id"]
                    ==user_id
                    and data["holder_since"]
                ):
                    stamps.append(
                        data["holder_since"]
                        +relic.REVENGE
                    )

                stamp=(
                    max(stamps)
                    if stamps
                    else 0
                )

                state=wait(stamp)

                if stamp<=now:
                    ready.append(
                        "`/relic` steal"
                    )

            add(
                events,
                "relic",
                f"{state} ⊹ ends "
                f"<t:{int(data['ends_at'])}:R>"
            )
    except Exception:
        pass

    try:
        drops=importlib.import_module(
            "commands.drops"
        )

        data=drops.live(
            guild_id
        )

        if data:
            add(
                events,
                "drops",
                f"live ⊹ "
                f"{data['remaining']:,} left "
                f"⊹ ends "
                f"<t:{int(data['ends_at'])}:R>"
            )

            ready.append(
                "`/drops`"
            )

        else:
            scheduled=drops.scheduled(
                guild_id
            )

            if scheduled:
                data=scheduled[0]

                add(
                    events,
                    "drops",
                    f"next "
                    f"<t:{int(data['start_at'])}:R>"
                )
    except Exception:
        pass

    try:
        draw=importlib.import_module("commands.draw")
        round=draw.current()
        mine,_=draw.counts(user_id,round["id"])
        stamp=float(round["draws_at"])
        status=(
            f"draws <t:{int(stamp)}:R>"
            if stamp>now
            else "drawing now"
        )
        add(events,"draw",f"{status} ⊹ {mine}/{draw.LIMIT} tickets")
    except Exception:
        pass

    embed=discord.Embed(
        title="⏳ cooldowns",
        color=discord.Color.dark_red()
    )

    embed.add_field(
        name="✦ ready now",
        value=(
            " • ".join(
                dict.fromkeys(ready)
            )
            if ready
            else "nothing urgent"
        ),
        inline=False
    )

    embed.add_field(
        name=rosieemoji.ROSE + ' daily + gameplay',
        value=(
            "\n".join(daily)
            if daily
            else "nothing"
        ),
        inline=False
    )

    embed.add_field(
        name="🐾 pet",
        value="\n".join(petlines),
        inline=False
    )

    embed.add_field(
        name="🩸 events",
        value=(
            "\n".join(events)
            if events
            else "no active event reminders"
        ),
        inline=False
    )

    if reminders:
        embed.add_field(
            name="‼️ reminders",
            value="\n".join(
                dict.fromkeys(reminders)
            ),
            inline=False
        )

    embed.set_footer(
        text=(
            "refreshes live • "
            "daily resets at 12:00 AM ET"
        )
    )

    return embed

class CoolView(discord.ui.View):
    def __init__(
        self,
        user_id,
        guild_id
    ):
        super().__init__(
            timeout=300
        )

        self.user_id=user_id
        self.guild_id=guild_id

    @discord.ui.button(
        emoji="🔄",
        style=discord.ButtonStyle.secondary
    )
    async def refresh(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        if it.user.id!=self.user_id:
            await it.response.send_message(
                "make ur own /cooldowns",
                ephemeral=True
            )
            return

        await it.response.edit_message(
            embed=build(
                self.user_id,
                self.guild_id
            ),
            view=CoolView(
                self.user_id,
                self.guild_id
            )
        )

class Cooldowns(commands.Cog):
    @app_commands.command(
        name="cooldowns",
        description="see what's ready"
    )
    @app_commands.guild_only()
    async def cooldowns(
        self,
        it:discord.Interaction
    ):
        game.touch(
            it.user.id
        )

        await it.response.send_message(
            embed=build(
                it.user.id,
                it.guild.id
            ),
            view=CoolView(
                it.user.id,
                it.guild.id
            ),
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(
        Cooldowns()
    )
