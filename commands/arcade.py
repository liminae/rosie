import asyncio

import discord
from discord import app_commands
from discord.ext import commands
from discord.http import Route
from core import arcade
from core import petcatalog

LOCKS={}


def screen(match):
    game=match["game"]
    status=match["status"]
    a,b=match["challenger"],match["opponent"]
    lines=[f"<@{a}> vs <@{b}>",f"{game} • {status}"]
    if status=="pending":
        lines.extend(("","the doors are open. for now."))
    elif status in ("declined","expired"):
        lines.extend(("", "the doors have closed."))
    else:
        data=match["data"]
        if game=="rps":
            lines.append(f"score ⊹ **{match['score_a']}–{match['score_b']}** • first to 3")
        else:
            pets=data["pets"]
            if len(pets)<2:
                lines.append(f"pets chosen ⊹ **{len(pets)}/2**")
            else:
                def show(side):
                    item=pets[side]
                    spec=petcatalog.SPECIES[item["species"]]
                    return f"{spec['emoji']} **{item['name']}**"
                lines.extend((f"{show('a')} vs {show('b')}",
                              f"hp ⊹ **{data['hp']['a']}–{data['hp']['b']}** • stamina {data['stamina']['a']}/{data['stamina']['b']}"))
        if status=="playing":
            lines.append(f"round {match['round']} • ready {len(data['choices'])}/2" if match["stage"]=="moves" else "choose your pets")
        if data["last"]:
            lines.extend(("",data["last"]))
        if status=="finished":
            lines.extend(("", f"winner ⊹ <@{match['winner']}>" if match["winner"] else "draw"))
    return discord.Embed(title="🥀 the red room",description="\n".join(lines),color=discord.Color.dark_red())


def lobby():
    return discord.Embed(title="🌹 rosie's arcade",description=(
        "**the abandoned arcade · the red room**\n"
        "*bring a friend. settle the score.*\n\n"
        "✂️ **rps** ⊹ first to 3\n"
        "🐾 **petfight** ⊹ friendly companion duel\n"
        "🥀 **thorn & bloom** ⊹ coming soon"),color=discord.Color.dark_red())


def controls(match):
    if match["status"]=="pending":
        return InviteView(match["id"])
    if match["status"]=="playing":
        return MatchView(match["id"])
    if match["status"]=="finished":
        return DoneView(match["id"])
    return None


async def refresh(bot,match_id):
    lock=LOCKS.setdefault(match_id,asyncio.Lock())
    async with lock:
        match=arcade.get(match_id)
        if not match or not match["message_id"]:
            return
        channel=bot.get_channel(match["channel_id"])
        if channel is None:
            channel=await bot.fetch_channel(match["channel_id"])
        message=await channel.fetch_message(match["message_id"])
        await message.edit(embed=screen(match),view=controls(match))


async def reply(it,text):
    await it.response.send_message(text,ephemeral=True)


class InviteView(discord.ui.View):
    def __init__(self,match_id):
        super().__init__(timeout=None)
        for action,emoji,style in (("accept","✅",discord.ButtonStyle.success),
                                   ("decline","❌",discord.ButtonStyle.secondary)):
            button=discord.ui.Button(emoji=emoji,label=action,style=style,custom_id=f"rosie:arcade:{match_id}:{action}")
            async def click(it,choice=action):
                match=arcade.get(match_id)
                if not match or it.guild_id!=match["guild_id"]:
                    return await reply(it,"that match is gone")
                result,_=arcade.decision(match_id,it.user.id,choice)
                if result!="ok":
                    return await reply(it,"that invite isn't yours or has expired")
                await it.response.defer()
                await refresh(it.client,match_id)
            button.callback=click
            self.add_item(button)


class MoveView(discord.ui.View):
    def __init__(self,match_id,game):
        super().__init__(timeout=180)
        for choice,emoji in (("rock","🪨"),("paper","📄"),("scissors","✂️")) if game=="rps" else (("strike","⚔️"),("guard","🛡️"),("trick","🎭")):
            button=discord.ui.Button(label=choice,emoji=emoji,style=discord.ButtonStyle.secondary)
            async def click(it,move=choice):
                result,_=arcade.move(match_id,it.user.id,move)
                if result in ("waiting","round","finished"):
                    await reply(it,"move locked ✓" if result=="waiting" else "round settled ✓")
                    await refresh(it.client,match_id)
                else:
                    await reply(it,{"already":"you already moved","stamina":"not enough stamina, guard to recover"}.get(result,"move unavailable"))
            button.callback=click
            self.add_item(button)


class PetPickView(discord.ui.View):
    def __init__(self,match_id,user_id):
        super().__init__(timeout=180)
        with arcade.connect() as con:
            pets=con.execute("SELECT species,name FROM pets WHERE user_id=? ORDER BY adopted_at",(user_id,)).fetchall()
        options=[]
        for p in pets[:25]:
            spec=petcatalog.SPECIES.get(p["species"])
            if spec:
                options.append(discord.SelectOption(label=p["name"][:100],value=p["species"],emoji=spec["emoji"]))
        if options:
            sel=discord.ui.Select(placeholder="choose your pet",options=options)
            async def choose(it):
                result,_=arcade.choose(match_id,it.user.id,sel.values[0])
                await reply(it,"pet selected ✓" if result=="picked" else "unable to select that pet")
                if result=="picked":
                    await refresh(it.client,match_id)
            sel.callback=choose
            self.add_item(sel)


class MatchView(discord.ui.View):
    def __init__(self,match_id):
        super().__init__(timeout=None)
        for name,emoji,style in (("move","🎮",discord.ButtonStyle.primary),
                                 ("forfeit","🏳️",discord.ButtonStyle.danger)):
            button=discord.ui.Button(emoji=emoji,label=name,style=style,custom_id=f"rosie:arcade:{match_id}:{name}")
            async def click(it,choice=name):
                match=arcade.get(match_id)
                if not match or it.guild_id!=match["guild_id"] or it.user.id not in (match["challenger"],match["opponent"]):
                    return await reply(it,"not your match")
                if choice=="forfeit":
                    result,_=arcade.forfeit(match_id,it.user.id)
                    if result!="finished":
                        return await reply(it,"match already closed")
                    await it.response.defer()
                    await refresh(it.client,match_id)
                    return
                if match["status"]!="playing":
                    return await reply(it,"match already closed")
                if match["stage"]=="pets":
                    view=PetPickView(match_id,it.user.id)
                    if not view.children:
                        return await reply(it,"adopt a pet using /pet first")
                    return await it.response.send_message("choose your fighter",view=view,ephemeral=True)
                await it.response.send_message("choose your move",view=MoveView(match_id,match["game"]),ephemeral=True)
            button.callback=click
            self.add_item(button)


class DoneView(discord.ui.View):
    def __init__(self,match_id):
        super().__init__(timeout=None)
        button=discord.ui.Button(emoji="🔁",label="rematch",style=discord.ButtonStyle.secondary,custom_id=f"rosie:arcade:{match_id}:rematch")
        async def click(it):
            prev=arcade.get(match_id)
            if not prev or prev["status"]!="finished" or it.guild_id!=prev["guild_id"] or it.user.id not in (prev["challenger"],prev["opponent"]):
                return await reply(it,"rematch unavailable")
            enemy=prev["opponent"] if it.user.id==prev["challenger"] else prev["challenger"]
            await challenge(it,enemy,prev["game"])
        button.callback=click
        self.add_item(button)


async def challenge(it,opponent_id,game):
    if not it.guild_id or not it.channel or opponent_id==it.user.id:
        return await reply(it,"pick another player")
    member=it.guild.get_member(opponent_id)
    if member is None:
        try:
            member=await it.guild.fetch_member(opponent_id)
        except discord.HTTPException:
            member=None
    if member is None or member.bot:
        return await reply(it,"choose a non-bot member of this server")
    result,match=arcade.create(it.guild_id,it.channel_id,it.user.id,opponent_id,game)
    if result!="ok":
        return await reply(it,"one of you is already in an arcade match" if result=="busy" else "invalid challenge")
    await it.response.defer(ephemeral=True)
    try:
        post=await it.channel.send(embed=screen(match),view=InviteView(match["id"]),allowed_mentions=discord.AllowedMentions(users=[member]))
        if not arcade.bind(match["id"],post.id):
            raise RuntimeError("could not attach match to message")
    except Exception:
        arcade.decision(match["id"],it.user.id,"decline")
        return await it.followup.send("arcade couldn't post the challenge",ephemeral=True)
    await it.followup.send("challenge sent ✓",ephemeral=True)


class SetupView(discord.ui.View):
    def __init__(self,user_id):
        super().__init__(timeout=180)
        self.user_id=user_id
        self.opponent=None
        self.game="rps"
        member=discord.ui.UserSelect(placeholder="choose a friend")
        async def select_user(it):
            self.opponent=member.values[0].id
            await it.response.defer()
        member.callback=select_user
        self.add_item(member)
        games=discord.ui.Select(placeholder="choose a game",options=[
            discord.SelectOption(label="rps",value="rps",emoji="✂️"),
            discord.SelectOption(label="petfight",value="petfight",emoji="🐾")])
        async def select_game(it):
            self.game=games.values[0]
            await it.response.defer()
        games.callback=select_game
        self.add_item(games)
        go=discord.ui.Button(label="challenge",emoji="⚔️",style=discord.ButtonStyle.danger)
        async def submit(it):
            if it.user.id!=self.user_id:
                return await reply(it,"not your challenge")
            if not self.opponent:
                return await reply(it,"choose a friend first")
            await challenge(it,self.opponent,self.game)
        go.callback=submit
        self.add_item(go)

    async def interaction_check(self,it):
        if it.user.id!=self.user_id:
            await reply(it,"not your menu")
            return False
        return True


class LobbyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for kind,emoji in (("challenge","⚔️"),("rivalries","🏆"),("rules","❔")):
            button=discord.ui.Button(label=kind,emoji=emoji,style=discord.ButtonStyle.secondary,custom_id=f"rosie:arcade:lobby:{kind}")
            async def click(it,action=kind):
                if action=="challenge":
                    return await it.response.send_message("pick a friend and a game",view=SetupView(it.user.id),ephemeral=True)
                if action=="rules":
                    return await reply(it,"rps: first to 3. petfight: strike, guard, or trick. no rose wagers. matches expire after inactivity.")
                records=arcade.records(it.guild_id,it.user.id)
                lines=[f"{game} ⊹ {data['wins']}w / {data['losses']}l / {data['draws']}d" for game,data in records.items()]
                await reply(it,"\n".join(lines))
            button.callback=click
            self.add_item(button)


class Arcade(commands.Cog):
    def __init__(self,bot):
        self.bot=bot
        self.published=False

    @commands.Cog.listener()
    async def on_ready(self):
        if self.published:
            return
        command=self.bot.tree.get_command("arcade")
        if command is None:
            print("arcade registry failed: local command missing")
            return
        try:
            application=self.bot.application_id
            assert application and application>0
            route="/applications/{application_id}/commands"
            body=command.to_dict(self.bot.tree)
            await self.bot.http.request(Route("POST",route,application_id=application),json=body)
            results=await self.bot.http.request(Route("GET",route,application_id=application))
            assert any(item.get("name")=="arcade" for item in results)
            self.published=True
            print("arcade command registry ✓")
        except Exception as error:
            print(f"arcade registry failed: {type(error).__name__}: {error}")

    @app_commands.command(name="arcade",description="bring a friend. settle the score.")
    @app_commands.guild_only()
    async def arcade(self,it:discord.Interaction):
        await it.response.send_message(embed=lobby(),view=LobbyView())


async def setup(bot):
    arcade.init()
    bot.add_view(LobbyView())
    for match in arcade.matches_to_restore():
        view=controls(match)
        if view:
            bot.add_view(view,message_id=match["message_id"])
    await bot.add_cog(Arcade(bot))
