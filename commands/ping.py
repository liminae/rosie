import discord
from core import reminders
from core import usage
from discord import app_commands
from discord.ext import commands,tasks
from core import emoji as rosieemoji

PING_ROLE="Rose ⋆‧°𓏲ּ𝄢"
LABELS={
    "daily":(rosieemoji.ROSE,"daily"),
    "pluck":(rosieemoji.ROSE,"pluck"),
    "garden":("🌱","garden"),
    "brew":("🧪","brew"),
    "quests":("📜","quests"),
    "campaign":(rosieemoji.ROSE,"campaign"),
    "pet":("🐾","pet"),
    "marriage":("💍","marriage"),
    "boss":("🩸","boss"),
    "reaper":("💀","reaper"),
    "relic":("🥀","relic"),
    "sin":("♦️","sin")
}

def role(guild):
    return discord.utils.get(guild.roles,name=PING_ROLE) if guild else None

async def syncroles(bot,user_id,value,current=None):
    failed=[]
    for guild in bot.guilds:
        if current is not None and getattr(getattr(current,"guild",None),"id",None)==guild.id:
            member=current
        else:
            member=guild.get_member(user_id)
            if member is None:
                try:
                    member=await guild.fetch_member(user_id)
                except (discord.NotFound,discord.Forbidden,discord.HTTPException):
                    continue
        reminders.note(user_id,guild.id)
        ping=role(guild)
        if ping is None:
            continue
        try:
            if value and ping not in member.roles:
                await member.add_roles(ping,reason="Rosie ping toggle")
            elif not value and ping in member.roles:
                await member.remove_roles(ping,reason="Rosie ping toggle")
        except (discord.Forbidden,discord.HTTPException):
            failed.append(guild.name)
    return failed

def panel(user_id):
    data=reminders.state(user_id)
    lines=[]
    for key in reminders.KEYS:
        emoji,label=LABELS[key]
        lines.append(f"{emoji} {label} ⊹ **{'on' if data['prefs'][key] else 'off'}**")
    return discord.Embed(
        title=rosieemoji.ROSE + ' notifications',
        description=(
            f"rose pings ⊹ **{'on' if data['rose'] else 'off'}**\n"
            f"dm reminders ⊹ **{'on' if data['dms'] else 'off'}**\n\n"
            +"\n".join(lines)
        ),
        color=discord.Color.dark_red()
    )

class Rose(discord.ui.Button):
    def __init__(self,user_id):
        data=reminders.state(user_id)
        super().__init__(
            emoji=rosieemoji.ROSE,
            style=discord.ButtonStyle.success if data["rose"] else discord.ButtonStyle.secondary,
            row=0
        )

    async def callback(self,it:discord.Interaction):
        view=self.view
        if it.user.id!=view.user_id:
            await it.response.send_message("make ur own /ping",ephemeral=True)
            return
        await it.response.defer()
        data=reminders.state(it.user.id)
        value=not data["rose"]
        reminders.setrose(it.user.id,value)
        failed=await syncroles(view.bot,it.user.id,value,it.user)
        await it.edit_original_response(
            embed=panel(it.user.id),
            view=Notify(view.bot,it.user.id)
        )
        text='rosie pings on ' + rosieemoji.ROSE + ' • dms on' if value else 'rosie pings off ' + rosieemoji.ROSE + ' • dms paused'
        if failed:
            text+="\nrosie couldnt reach the Rose role in "+", ".join(failed[:3])
        await it.followup.send(text,ephemeral=True)

class Dms(discord.ui.Button):
    def __init__(self,user_id):
        data=reminders.state(user_id)
        super().__init__(
            emoji="✉️",
            style=discord.ButtonStyle.success if data["dms"] else discord.ButtonStyle.secondary,
            disabled=not data["rose"],
            row=0
        )

    async def callback(self,it:discord.Interaction):
        view=self.view
        if it.user.id!=view.user_id:
            await it.response.send_message("make ur own /ping",ephemeral=True)
            return
        data=reminders.state(it.user.id)
        if not data["rose"]:
            await it.response.send_message('turn rose pings on first babe ' + rosieemoji.ROSE,ephemeral=True)
            return
        value=not data["dms"]
        reminders.setdms(it.user.id,value)
        await it.response.edit_message(
            embed=panel(it.user.id),
            view=Notify(view.bot,it.user.id)
        )
        await it.followup.send(
            f"dm reminders {'on' if value else 'off'} ✉️",
            ephemeral=True
        )

class Pick(discord.ui.Select):
    def __init__(self,user_id):
        data=reminders.state(user_id)
        options=[]
        for key in reminders.KEYS:
            emoji,label=LABELS[key]
            on=data["prefs"][key]
            options.append(
                discord.SelectOption(
                    label=label,
                    value=key,
                    emoji=emoji,
                    description="on • select to turn off" if on else "off • select to turn on"
                )
            )
        super().__init__(
            placeholder="toggle a reminder",
            min_values=1,
            max_values=1,
            options=options,
            row=1
        )

    async def callback(self,it:discord.Interaction):
        view=self.view
        if it.user.id!=view.user_id:
            await it.response.send_message("make ur own /ping",ephemeral=True)
            return
        reminders.toggle(it.user.id,self.values[0])
        await it.response.edit_message(
            embed=panel(it.user.id),
            view=Notify(view.bot,it.user.id)
        )

class Notify(discord.ui.View):
    def __init__(self,bot,user_id):
        super().__init__(timeout=600)
        self.bot=bot
        self.user_id=user_id
        self.add_item(Rose(user_id))
        self.add_item(Dms(user_id))
        self.add_item(Pick(user_id))

class Open(discord.ui.Button):
    def __init__(self):
        super().__init__(emoji=rosieemoji.ROSE,style=discord.ButtonStyle.secondary)

    async def callback(self,it:discord.Interaction):
        view=self.view
        await it.response.defer(ephemeral=True,thinking=True)
        new=reminders.register(
            it.user.id,
            it.guild.id if it.guild else None
        )
        data=reminders.state(it.user.id)
        failed=await syncroles(
            view.bot,
            it.user.id,
            data["rose"],
            it.user if it.guild else None
        )
        if new:
            reminders.primeall(it.user.id)
        await it.edit_original_response(
            embed=panel(it.user.id),
            view=Notify(view.bot,it.user.id)
        )
        if failed:
            await it.followup.send(
                "rosie couldnt reach the Rose role in "+", ".join(failed[:3]),
                ephemeral=True
            )

class PingView(discord.ui.View):
    def __init__(self,bot):
        super().__init__(timeout=3600)
        self.bot=bot
        self.add_item(Open())

class Ping(commands.Cog):
    def __init__(self,bot):
        self.bot=bot
        reminders.init()
        self.clock.start()

    def cog_unload(self):
        self.clock.cancel()

    @tasks.loop(seconds=30)
    async def clock(self):
        for user_id in reminders.users():
            events=reminders.due(user_id)
            if not events:
                continue
            user=self.bot.get_user(user_id)
            if user is None:
                try:
                    user=await self.bot.fetch_user(user_id)
                except discord.HTTPException:
                    continue
            name=getattr(user,"display_name",user.name)
            for event in events:
                guild_id=event.get("guild_id")
                found=self.bot.get_guild(guild_id) if guild_id is not None else None
                text=reminders.message(
                    name,
                    event,
                    found.name if found else None
                )
                try:
                    await user.send(text)
                except discord.Forbidden:
                    reminders.setdms(user_id,False)
                    break
                except discord.HTTPException:
                    continue
                reminders.mark(user_id,event)

    @clock.before_loop
    async def before(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="ping",description="is rosie alive")
    async def ping(self,it:discord.Interaction):
        data=usage.stats(it.user.id)
        latency=round(self.bot.latency*1000)
        text=(
            f"latency ⊹ **{latency:,} ms**\n"
            f"you ⊹ **{data['mine']:,} commands**\n"
            f"users ⊹ **{data['users']:,}**\n"
            f"total ⊹ **{data['total']:,} commands**\n"
            f"since ⊹ <t:{int(data['started'])}:D>"
        )
        await it.response.send_message(
            embed=discord.Embed(
                title="🏓 pong",
                description=text,
                color=discord.Color.dark_red()
            ),
            view=PingView(self.bot)
        )

async def setup(bot):
    await bot.add_cog(Ping(bot))
