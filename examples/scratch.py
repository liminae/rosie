import discord
from core import database
from core import game
from discord import app_commands
from discord.ext import commands
from core import emoji as rosieemoji

class ScratchTile(discord.ui.Button):
    def __init__(self,index):
        super().__init__(label="✦",style=discord.ButtonStyle.danger,row=index//3)
        self.index=index

    async def callback(self,it:discord.Interaction):
        view=self.view
        if it.user.id!=view.user_id:
            await it.response.send_message("not ur scratch card",ephemeral=True)
            return
        state,prize=game.reveal_scratch(view.user_id,self.index)
        if state is None:
            await it.response.send_message("card vanished 💔 run /scratch again",ephemeral=True)
            return
        if prize is not None:
            emoji,kind,value,name=game.CARDS[state["card"]][prize]
            if kind=="rings":
                database.walletadd(view.guild_id,view.user_id,rings=value)
            else:
                database.walletadd(view.guild_id,view.user_id,roses=value)
        view.state=state
        view.refresh()
        await it.response.edit_message(embed=view.embed(),view=view)

class ScratchView(discord.ui.View):
    def __init__(self,user_id,state,display_name,guild_id):
        super().__init__(timeout=300)
        self.user_id=user_id
        self.state=state
        self.display_name=display_name
        self.guild_id=guild_id
        for i in range(12):
            self.add_item(ScratchTile(i))
        self.refresh()

    def prizes_found(self):
        found=[]
        for index in self.state["revealed"]:
            prize=self.state["board"][index]
            if prize>=0:
                found.append(prize)
        return found

    def refresh(self):
        prizes=game.CARDS[self.state["card"]]
        for item in self.children:
            if not isinstance(item,ScratchTile):
                continue
            if item.index in self.state["revealed"]:
                prize=self.state["board"][item.index]
                item.style=discord.ButtonStyle.secondary
                item.disabled=True
                if prize>=0:
                    item.label=None
                    item.emoji=prizes[prize][0]
                else:
                    item.label="✦"
                    item.emoji=None
            else:
                item.label="✦"
                item.emoji=None
                item.style=discord.ButtonStyle.danger
                item.disabled=self.state["finished"]

    def embed(self):
        prizes=game.CARDS[self.state["card"]]
        rewards="\n".join(f"{emoji} • {name}" for emoji,kind,value,name in prizes)
        left=max(0,4-len(self.state["revealed"]))
        found=self.prizes_found()
        jackpot=len(set(found))==3
        reset=int(game.next_reset().timestamp())
        if self.state["finished"] and jackpot:
            won="\n".join(f"⊹ {prizes[prize][3]}" for prize in found)
            ending=f"✦ **jackpot**\n{won}\n\nnew card • <t:{reset}:R>"
        elif self.state["finished"] and found:
            won="\n".join(f"⊹ {prizes[prize][3]}" for prize in found)
            ending=f"**you found**\n{won}\n\nnew card • <t:{reset}:R>"
        elif self.state["finished"]:
            ending="loser loser"
        elif jackpot:
            ending=f"✦ **jackpot**\n\n**{left} scratch{'es' if left!=1 else ''} left**"
        else:
            ending=f"**{left} scratch{'es' if left!=1 else ''} left**"
        return discord.Embed(title=f"🎟️ {self.display_name}'s scratch-off",description=f"**possible rewards**\n{rewards}\n\n{ending}",color=discord.Color.dark_red())

class Scratch(commands.Cog):
    @app_commands.command(name="scratch",description="scratch today's card")
    @app_commands.guild_only()
    async def scratch(self,it:discord.Interaction):
        if not game.has_daily(it.user.id):
            await it.response.send_message('grab /daily first ' + rosieemoji.ROSE,ephemeral=True)
            return
        state=game.start_scratch(it.user.id)
        view=ScratchView(it.user.id,state,it.user.display_name,it.guild_id)
        await it.response.send_message(embed=view.embed(),view=view)

async def setup(bot):
    await bot.add_cog(Scratch())
