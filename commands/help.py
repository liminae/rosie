import discord
from discord import app_commands
from discord.ext import commands
from core import emoji as rosieemoji

CATEGORIES=(
    (
        rosieemoji.ROSE + ' economy',
        (
            "balance",
            "daily",
            "pluck",
            "garden",
            "forage",
            "brew",
            "roots",
            "quests",
            "transfer",
            "redeem"
        )
    ),
    (
        "🎰 games",
        (
            "blackjack",
            "box",
            "campaign",
            "cf",
            "scratch",
            "slots",
            "odds"
        )
    ),
    (
        "🩸 events",
        (
            "boss",
            "drops",
            "reaper",
            "relic",
            "rune",
            "sin"
        )
    ),
    (
        "💌 social",
        (
            "pet",
            "leaderboard",
            "marriage"
        )
    ),
    (
        "⚙️ rosie",
        (
            "cooldowns",
            "help",
            "ping"
        )
    )
)

def embed(bot):
    hidden={
        "give",
        "take",
        "usage",
        "economy",
        "roses",
        "settings"
    }

    commands={
        command.name:command
        for command in bot.tree.get_commands()
        if command.name not in hidden
    }

    out=discord.Embed(
        title=rosieemoji.ROSE + ' rosie',
        color=discord.Color.dark_red()
    )

    used=set()

    for title,names in CATEGORIES:
        found=[
            commands[name]
            for name in names
            if name in commands
        ]

        if not found:
            continue

        used.update(
            command.name
            for command in found
        )

        out.add_field(
            name=title,
            value="\n".join(
                f"`/{command.name}` ⊹ "
                f"{command.description}"
                for command in found
            ),
            inline=False
        )

    extras=[]

    if "draw" in commands:
        used.add("draw")
        extras.append(
            "`/draw` ⊹ open rosie's draw"
        )

    if "parlor" in commands:
        used.add("parlor")
        extras.append(
            "`/parlor` ⊹ open rosie's parlor"
        )

    if "season" in commands:
        used.add("season")
        extras.append(
            "`/season` ⊹ open rosie's season"
        )

    if extras:
        out.add_field(
            name="🎴 extras",
            value="\n".join(
                extras
            ),
            inline=False
        )

    other=sorted(
        (
            command
            for name,command in commands.items()
            if name not in used
        ),
        key=lambda command:command.name
    )

    if other:
        out.add_field(
            name="✦ other",
            value="\n".join(
                f"`/{command.name}` ⊹ "
                f"{command.description}"
                for command in other
            ),
            inline=False
        )

    return out

class Help(commands.Cog):
    def __init__(self,bot):
        self.bot=bot

    @app_commands.command(
        name="help",
        description="see rosie's commands"
    )
    @app_commands.guild_only()
    async def help(
        self,
        it:discord.Interaction
    ):
        await it.response.send_message(
            embed=embed(self.bot),
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(
        Help(bot)
    )
