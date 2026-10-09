import asyncio
import re

import discord
from core import database
from core import embedtheme
from core import fulfillment
from core import game
from core import rewardshop
from discord import app_commands
from discord.ext import commands
from discord.http import Route

HOLDINGS={
    "nitro_basic":("💙","nitro basic • 1 month"),
    "nitro":("💜","nitro • 1 month"),
    "steam_game":("🎮","steam game")
}

COLOR_TOKEN="cosmetic:embed_color"


async def member(
    guild,
    user_id
):
    if not user_id:
        return None

    found=guild.get_member(
        user_id
    )

    if found is not None:
        return found

    try:
        return await guild.fetch_member(
            user_id
        )

    except discord.HTTPException:
        return None


async def maketicket(
    bot,
    it,
    handler_id
):
    app=await bot.application_info()

    owner=await member(
        it.guild,
        app.owner.id
    )

    staff=await member(
        it.guild,
        handler_id
    )

    category=next(
        (
            x
            for x in it.guild.categories
            if x.name.lower()=="redemptions"
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
            overwrites[
                owner
            ]=allow

        if staff is not None:
            overwrites[
                staff
            ]=allow

        channel=await it.guild.create_text_channel(
            f"redeem-{it.user.id}",
            category=category,
            overwrites=overwrites,
            reason=f"redemption by {it.user}"
        )

        return channel,None

    except discord.Forbidden:
        return (
            None,
            "i cant make redemption tickets 💔"
        )

    except discord.HTTPException:
        return (
            None,
            "ticket machine died 💔 try again"
        )


def mention(
    handler_id
):
    return (
        f"<@{handler_id}> pay up ahaha"
        if handler_id
        else "waiting on fulfillment"
    )


def buildshop(
    guild_id,
    user_id
):
    rewardshop.init()

    _,rings=database.wallet(
        guild_id,
        user_id
    )

    items=[]

    for row in rewardshop.shop(
        guild_id
    ):
        row=dict(
            row
        )

        price=int(
            row[
                "ring_price"
            ]
        )

        items.append({
            "source":"reward",
            "token":(
                "reward:"
                +row[
                    "reward_key"
                ]
            ),
            "reward_key":
                row[
                    "reward_key"
                ],
            "label":
                row[
                    "label"
                ],
            "emoji":
                row[
                    "emoji"
                ]
                or "🎁",
            "unit_cost":price,
            "balance":rings,
            "max_quantity":(
                rings//price
            )
        })

    items.append({
        "source":"cosmetic",
        "token":COLOR_TOKEN,
        "label":"embed color",
        "emoji":"🎨",
        "unit_cost":embedtheme.PRICE,
        "balance":rings,
        "max_quantity":(
            1
            if rings>=embedtheme.PRICE
            else 0
        )
    })

    for kind,(
        emoji,
        label
    ) in HOLDINGS.items():
        balance=database.item(
            user_id,
            kind
        )

        if balance<1:
            continue

        items.append({
            "source":"holding",
            "token":(
                "holding:"
                +kind
            ),
            "kind":kind,
            "label":label,
            "emoji":emoji,
            "unit_cost":0,
            "balance":balance,
            "max_quantity":balance
        })

    return (
        items,
        rings
    )


def shopembed(
    items,
    rings
):
    names={
        "nitro_basic":"basic nitro",
        "nitro":"nitro",
        "steam_game":"steam game"
    }

    held=[]

    for item in items:
        if (
            item[
                "source"
            ]!="holding"
            or int(
                item[
                    "balance"
                ]
            )<1
        ):
            continue

        held.append(
            f"{item['emoji']} "
            f"**{item['balance']:,}** "
            f"{names.get(item['kind'],item['label'])}"
        )

    holdings=(
        " • ".join(
            held
        )
        if held
        else "**none**"
    )

    rewards=[]

    for item in items:
        if item[
            "source"
        ] not in (
            "reward",
            "cosmetic"
        ):
            continue

        price=int(
            item[
                "unit_cost"
            ]
        )

        label=str(
            item[
                "label"
            ]
        ).replace(
            "Robux",
            "robux"
        )

        rewards.append(
            f"{item['emoji']} "
            f"**{label}** ⊹ "
            f"**{price:,} "
            f"{'ring' if price==1 else 'rings'}** 💍"
        )

    text=(
        "pick ur prize heh\n\n"
        f"rings ⊹ **{rings:,}** 💍\n"
        f"holdings ⊹ {holdings}"
    )

    if rewards:
        text+=(
            "\n\n"
            +"\n".join(
                rewards
            )
        )

    return discord.Embed(
        title="🎁 redeem",
        description=text,
        color=discord.Color.dark_red()
    )








def orderembed(
    order,
    quantity
):
    quantity=int(
        quantity
    )

    label=str(
        order[
            "label"
        ]
    ).replace(
        "Robux",
        "robux"
    )

    if (
        order[
            "source"
        ]=="reward"
    ):
        unit=int(
            order[
                "unit_cost"
            ]
        )

        total=(
            unit
            *quantity
        )

        detail=(
            f"item ⊹ {order['emoji']} "
            f"**{label}**\n"
            f"quantity ⊹ **{quantity:,}**\n"
            f"unit price ⊹ **{unit:,} "
            f"{'ring' if unit==1 else 'rings'}** 💍\n"
            f"total ⊹ **{total:,} "
            f"{'ring' if total==1 else 'rings'}** 💍\n"
            f"rings ⊹ **{order['balance']:,}** 💍"
        )

    else:
        detail=(
            f"item ⊹ {order['emoji']} "
            f"**{label}**\n"
            f"quantity ⊹ **{quantity:,}**\n"
            f"owned ⊹ **{order['balance']:,}**"
        )

    return discord.Embed(
        description=detail,
        color=discord.Color.dark_red()
    )




class RewardQuantityModal(
    discord.ui.Modal
):
    def __init__(
        self,
        cog,
        user_id,
        token,
        order
    ):
        super().__init__(
            title="redeem quantity",
            timeout=60
        )

        self.cog=cog
        self.user_id=int(
            user_id
        )
        self.token=token

        maximum=max(
            1,
            int(
                order[
                    "max_quantity"
                ]
            )
        )

        self.quantity=discord.ui.TextInput(
            label="quantity",
            placeholder=(
                f"1 - {maximum:,}"
            ),
            default="1",
            min_length=1,
            max_length=8,
            required=True
        )

        self.add_item(
            self.quantity
        )

    async def on_submit(
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
            return

        try:
            quantity=int(
                str(
                    self.quantity.value
                ).strip()
            )

        except ValueError:
            await it.response.send_message(
                "gimme a real quantity",
                ephemeral=True
            )
            return

        order=self.cog.orderinfo(
            it.guild.id,
            it.user.id,
            self.token
        )

        if order is None:
            await it.response.send_message(
                "that item isnt available anymore",
                ephemeral=True
            )
            return

        maximum=int(
            order[
                "max_quantity"
            ]
        )

        if maximum<1:
            message=(
                "ur ringless 💔"
                if order[
                    "source"
                ]=="reward"
                else "you dont have any of that"
            )

            await it.response.send_message(
                message,
                ephemeral=True
            )
            return

        if (
            quantity<1
            or quantity>maximum
        ):
            await it.response.send_message(
                f"pick 1 - {maximum:,}",
                ephemeral=True
            )
            return

        await it.response.send_message(
            embed=orderembed(
                order,
                quantity
            ),
            view=RedeemConfirmView(
                self.cog,
                it.user.id,
                self.token,
                quantity
            ),
            ephemeral=True
        )



def colorpreview(color):
    return embedtheme.fixed(
        discord.Embed(
            title="🎨 embed color",
            description=(
                f"new color ⊹ "
                f"**{embedtheme.hexcolor(color)}**\n"
                f"default ⊹ "
                f"**{embedtheme.DEFAULT_HEX}**\n"
                f"cost ⊹ "
                f"**{embedtheme.PRICE} ring** 💍\n\n"
                "one purchase = one change"
            ),
            color=discord.Colour(
                color
            )
        )
    )


def colorchanged(
    color,
    balance
):
    return embedtheme.fixed(
        discord.Embed(
            title="🎨 embed color",
            description=(
                f"changed ⊹ "
                f"**{embedtheme.hexcolor(color)}**\n"
                f"rings ⊹ "
                f"**{balance:,}** 💍\n\n"
                "another change costs "
                f"**{embedtheme.PRICE} ring** 💍"
            ),
            color=discord.Colour(
                color
            )
        )
    )


class EmbedColorConfirmView(
    discord.ui.View
):
    def __init__(
        self,
        user_id,
        color
    ):
        super().__init__(
            timeout=60
        )

        self.user_id=int(
            user_id
        )

        self.color=int(
            color
        )

        self.used=False

    @discord.ui.button(
        emoji="✅",
        style=discord.ButtonStyle.success
    )
    async def confirm(
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

        if self.used:
            await it.response.send_message(
                "already submitted",
                ephemeral=True
            )
            return

        self.used=True

        result=embedtheme.purchase(
            it.guild.id,
            it.user.id,
            self.color
        )

        if not result[
            "ok"
        ]:
            await it.response.edit_message(
                content="ur ringless 💔",
                embed=None,
                view=None
            )
            return

        game.bump(
            it.user.id,
            "rings_redeemed",
            result[
                "cost"
            ]
        )

        await it.response.edit_message(
            content=None,
            embed=colorchanged(
                result[
                    "color"
                ],
                result[
                    "balance"
                ]
            ),
            view=None
        )

    @discord.ui.button(
        emoji="❌",
        style=discord.ButtonStyle.danger
    )
    async def cancel(
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

        self.used=True

        await it.response.edit_message(
            content="canceled",
            embed=None,
            view=None
        )


class EmbedColorModal(
    discord.ui.Modal
):
    def __init__(
        self,
        user_id
    ):
        super().__init__(
            title="embed color",
            timeout=60
        )

        self.user_id=int(
            user_id
        )

        self.color=discord.ui.TextInput(
            label="hex color",
            placeholder=embedtheme.DEFAULT_HEX,
            min_length=6,
            max_length=7,
            required=True
        )

        self.add_item(
            self.color
        )

    async def on_submit(
        self,
        it:discord.Interaction
    ):
        if it.user.id!=self.user_id:
            await it.response.send_message(
                "nuh uh",
                ephemeral=True
            )
            return

        try:
            color=embedtheme.normalize(
                self.color.value
            )

        except ValueError:
            await it.response.send_message(
                f"use a hex color like "
                f"{embedtheme.DEFAULT_HEX}",
                ephemeral=True
            )
            return

        _,rings=database.wallet(
            it.guild.id,
            it.user.id
        )

        if rings<embedtheme.PRICE:
            await it.response.send_message(
                "ur ringless 💔",
                ephemeral=True
            )
            return

        await it.response.send_message(
            embed=colorpreview(
                color
            ),
            view=EmbedColorConfirmView(
                it.user.id,
                color
            ),
            ephemeral=True
        )


class RewardShopSelect(
    discord.ui.Select
):
    def __init__(
        self,
        cog,
        user_id,
        items
    ):
        self.cog=cog
        self.user_id=int(
            user_id
        )

        names={
            "nitro_basic":"basic nitro",
            "nitro":"nitro",
            "steam_game":"steam game"
        }

        options=[]

        for item in items[:25]:
            if item[
                "source"
            ] in (
                "reward",
                "cosmetic"
            ):
                price=int(
                    item[
                        "unit_cost"
                    ]
                )

                label=str(
                    item[
                        "label"
                    ]
                ).replace(
                    "Robux",
                    "robux"
                )

                if item[
                    "source"
                ]=="cosmetic":
                    description=(
                        f"{price:,} "
                        f"{'ring' if price==1 else 'rings'} "
                        "💍 ⊹ one change"
                    )
                else:
                    description=(
                        f"{price:,} "
                        f"{'ring' if price==1 else 'rings'} "
                        f"💍 ⊹ up to "
                        f"{item['max_quantity']:,}"
                    )

            else:
                label=names.get(
                    item[
                        "kind"
                    ],
                    item[
                        "label"
                    ]
                )

                description=(
                    f"owned • "
                    f"{item['balance']:,}"
                )

            options.append(
                discord.SelectOption(
                    emoji=item[
                        "emoji"
                    ],
                    label=label[
                        :100
                    ],
                    description=description[
                        :100
                    ],
                    value=item[
                        "token"
                    ]
                )
            )

        super().__init__(
            placeholder="pick an item",
            options=options
        )

    async def callback(
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
            return

        token=self.values[
            0
        ]

        order=self.cog.orderinfo(
            it.guild.id,
            it.user.id,
            token
        )

        if order is None:
            await it.response.send_message(
                "that item isnt available anymore",
                ephemeral=True
            )
            return

        if int(
            order[
                "max_quantity"
            ]
        )<1:
            message=(
                "ur ringless 💔"
                if order[
                    "source"
                ] in (
                    "reward",
                    "cosmetic"
                )
                else "you dont have any of that"
            )

            await it.response.send_message(
                message,
                ephemeral=True
            )
            return

        if order[
            "source"
        ]=="cosmetic":
            await it.response.send_modal(
                EmbedColorModal(
                    it.user.id
                )
            )
            return

        await it.response.send_modal(
            RewardQuantityModal(
                self.cog,
                it.user.id,
                token,
                order
            )
        )



class RewardShopView(
    discord.ui.View
):
    def __init__(
        self,
        cog,
        user_id,
        items
    ):
        super().__init__(
            timeout=120
        )

        self.add_item(
            RewardShopSelect(
                cog,
                user_id,
                items
            )
        )


class RedeemConfirmView(
    discord.ui.View
):
    def __init__(
        self,
        cog,
        user_id,
        token,
        quantity
    ):
        super().__init__(
            timeout=60
        )

        self.cog=cog
        self.user_id=int(
            user_id
        )
        self.token=token
        self.quantity=int(
            quantity
        )
        self.used=False

    @discord.ui.button(
        emoji='✅',
        style=discord.ButtonStyle.success
    )
    async def confirm(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        if (
            it.user.id
            !=self.user_id
        ):
            await it.response.send_message(
                "nuh uh",
                ephemeral=True
            )
            return

        if self.used:
            await it.response.send_message(
                "already submitted",
                ephemeral=True
            )
            return

        self.used=True

        for child in self.children:
            child.disabled=True

        await it.response.edit_message(
            view=self
        )

        await self.cog.confirmorder(
            it,
            self.token,
            self.quantity
        )

    @discord.ui.button(
        emoji='❌',
        style=discord.ButtonStyle.danger
    )
    async def cancel(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        if (
            it.user.id
            !=self.user_id
        ):
            await it.response.send_message(
                "nuh uh",
                ephemeral=True
            )
            return

        self.used=True

        await it.response.edit_message(
            content="canceled",
            embed=None,
            view=None
        )


class RedeemView(discord.ui.View):
    def __init__(self,bot):
        super().__init__(timeout=None)
        self.bot=bot

    @discord.ui.button(
        emoji="🗑️",
        style=discord.ButtonStyle.danger,
        custom_id="rosie:close_redeem"
    )
    async def close(
        self,
        it:discord.Interaction,
        button:discord.ui.Button
    ):
        topic=it.channel.topic or ""

        match=(
            re.search(r"claim:(\d+)",topic)
            or re.search(r"claim #(\d+)",topic)
        )

        claim=(
            int(
                match.group(1)
            )
            if match
            else None
        )

        meta=(
            rewardshop.claimmeta(
                claim
            )
            if claim is not None
            else None
        )

        kind=(
            meta["fulfillment"]
            if meta is not None
            else "reward"
        )

        allowed=(
            (
                int(meta["handler_id"])
                if (
                    meta is not None
                    and meta["handler_id"] is not None
                )
                else None
            )
            or fulfillment.handler(
                it.guild.id,
                kind
            )
            or fulfillment.handler(
                it.guild.id,
                "reward"
            )
        )

        if (
            it.user.id!=allowed
            and not await self.bot.is_owner(
                it.user
            )
        ):
            await it.response.send_message(
                "nuh uh",
                ephemeral=True
            )
            return

        await it.response.send_message(
            "closing heh",
            ephemeral=True
        )

        await asyncio.sleep(1)

        await it.channel.delete(
            reason=f"redemption closed by {it.user}"
        )

        if claim is not None:
            database.close_claim(
                claim
            )

            if meta is not None:
                fulfillment.close(
                    it.guild.id,
                    kind,
                    claim
                )

            else:
                game.close_redemption(
                    claim
                )


class Redeem(commands.Cog):
    def __init__(
        self,
        bot
    ):
        self.bot=bot
        self.registry_done=False

    async def registry(
        self
    ):
        if self.registry_done:
            return

        app_id=(
            self.bot.application_id
            or self.bot.user.id
        )

        rows=await self.bot.http.get_global_commands(
            app_id
        )

        row=next(
            (
                item
                for item in rows
                if (
                    item.get(
                        "name"
                    )=="redeem"
                    and int(
                        item.get(
                            "type",
                            1
                        )
                    )==1
                )
            ),
            None
        )

        payload={
            "name":"redeem",
            "description":"open the redeem",
            "type":1,
            "dm_permission":False,
            "options":[]
        }

        if row is None:
            route=Route(
                "POST",
                "/applications/{application_id}/commands",
                application_id=app_id
            )

        else:
            route=Route(
                "PATCH",
                "/applications/{application_id}/commands/{command_id}",
                application_id=app_id,
                command_id=row[
                    "id"
                ]
            )

        await self.bot.http.request(
            route,
            json=payload
        )

        self.registry_done=True

        print(
            "redeem command registry ✓"
        )

    @commands.Cog.listener()
    async def on_ready(
        self
    ):
        try:
            await self.registry()

        except Exception as error:
            print(
                f"redeem registry failed ⊹ "
                f"{error}"
            )

    def orderinfo(
        self,
        guild_id,
        user_id,
        token
    ):
        token=str(
            token
        )

        if token==COLOR_TOKEN:
            _,rings=database.wallet(
                guild_id,
                user_id
            )

            return {
                "source":"cosmetic",
                "token":COLOR_TOKEN,
                "label":"embed color",
                "emoji":"🎨",
                "unit_cost":embedtheme.PRICE,
                "balance":rings,
                "max_quantity":(
                    1
                    if rings>=embedtheme.PRICE
                    else 0
                )
            }

        if token.startswith(
            "reward:"
        ):
            reward_key=token.split(
                ":",
                1
            )[1]

            data=rewardshop.item(
                guild_id,
                reward_key
            )

            if (
                data is None
                or not data[
                    "active"
                ]
            ):
                return None

            data=dict(
                data
            )

            _,rings=database.wallet(
                guild_id,
                user_id
            )

            price=int(
                data[
                    "ring_price"
                ]
            )

            return {
                "source":"reward",
                "token":token,
                "reward_key":
                    reward_key,
                "label":
                    data[
                        "label"
                    ],
                "emoji":
                    data[
                        "emoji"
                    ]
                    or "🎁",
                "unit_cost":price,
                "balance":rings,
                "max_quantity":(
                    rings//price
                )
            }

        if token.startswith(
            "holding:"
        ):
            kind=token.split(
                ":",
                1
            )[1]

            if kind not in HOLDINGS:
                return None

            emoji,label=HOLDINGS[
                kind
            ]

            balance=database.item(
                user_id,
                kind
            )

            return {
                "source":"holding",
                "token":token,
                "kind":kind,
                "label":label,
                "emoji":emoji,
                "unit_cost":0,
                "balance":balance,
                "max_quantity":balance
            }

        return None

    async def confirmorder(
        self,
        it,
        token,
        quantity
    ):
        quantity=int(
            quantity
        )

        if quantity<1:
            await it.followup.send(
                "gimme a real quantity",
                ephemeral=True
            )
            return

        order=self.orderinfo(
            it.guild.id,
            it.user.id,
            token
        )

        if order is None:
            await it.followup.send(
                "that item isnt available anymore",
                ephemeral=True
            )
            return

        maximum=int(
            order[
                "max_quantity"
            ]
        )

        if quantity>maximum:
            await it.followup.send(
                (
                    f"you can only redeem "
                    f"{maximum:,} rn"
                ),
                ephemeral=True
            )
            return

        if (
            order[
                "source"
            ]=="reward"
        ):
            reward_key=order[
                "reward_key"
            ]

            data=rewardshop.item(
                it.guild.id,
                reward_key
            )

            if (
                data is None
                or not data[
                    "active"
                ]
            ):
                await it.followup.send(
                    "that reward isnt available anymore",
                    ephemeral=True
                )
                return

            configured_handler=None

            if (
                "handler_id"
                in data.keys()
            ):
                configured_handler=data[
                    "handler_id"
                ]

            kind=data[
                "fulfillment"
            ]

            handler_id=(
                configured_handler
                or fulfillment.handler(
                    it.guild.id,
                    kind
                )
                or fulfillment.handler(
                    it.guild.id,
                    "reward"
                )
            )

            channel,error=await maketicket(
                self.bot,
                it,
                handler_id
            )

            if channel is None:
                await it.followup.send(
                    error,
                    ephemeral=True
                )
                return

            result=rewardshop.redeem(
                it.guild.id,
                reward_key,
                it.user.id,
                source="redeem",
                quantity=quantity
            )

            if not result[
                "ok"
            ]:
                await channel.delete(
                    reason="redemption failed"
                )

                await it.followup.send(
                    (
                        "ur ringless 💔"
                        if result[
                            "reason"
                        ]=="broke"
                        else
                        "that reward isnt available anymore"
                    ),
                    ephemeral=True
                )
                return

            claim=result[
                "claim"
            ]

            data=result[
                "item"
            ]

            cost=result[
                "ring_cost"
            ]

            quantity=result[
                "quantity"
            ]

            game.bump(
                it.user.id,
                "rings_redeemed",
                cost
            )

            fulfillment.record(
                it.guild.id,
                data[
                    "fulfillment"
                ],
                claim,
                it.user.id,
                data
            )

            instruction=fulfillment.instructions(
                it.guild.id,
                data[
                    "fulfillment"
                ]
            )

            detail=(
                f"reward • "
                f"{data['emoji'] or '🎁'} "
                f"**{quantity:,}× "
                f"{data['label']}**\\n"
                f"cost • **{cost:,} "
                f"{'ring' if cost==1 else 'rings'}** 💍"
            )

            if instruction:
                detail+=(
                    f"\\n{instruction}"
                )

            try:
                await channel.edit(
                    name=f"redeem-{claim}",
                    topic=(
                        f"claim:{claim} • "
                        f"user:{it.user.id} • "
                        f"kind:shop:"
                        f"{data['reward_key']}"
                    )
                )

            except discord.HTTPException:
                pass

            receipt=await channel.send(
                f"🎟️ **redemption #{claim}**\\n"
                f"redeemer • {it.user.mention} "
                f"(`{it.user.id}`)\\n"
                f"{detail}\\n\\n"
                f"{mention(handler_id)}",
                view=RedeemView(
                    self.bot
                )
            )

            try:
                await receipt.pin(
                    reason="redemption receipt"
                )

            except discord.HTTPException:
                pass

            await it.followup.send(
                f"ticket ⊹ {channel.mention}\\n"
                f"claim #{claim} • "
                f"**{quantity:,}× "
                f"{data['label']}**",
                ephemeral=True
            )

            return

        kind=order[
            "kind"
        ]

        emoji,label=HOLDINGS[
            kind
        ]

        handler_id=fulfillment.handler(
            it.guild.id,
            "reward"
        )

        channel,error=await maketicket(
            self.bot,
            it,
            handler_id
        )

        if channel is None:
            await it.followup.send(
                error,
                ephemeral=True
            )
            return

        claim=database.redeem_item(
            it.user.id,
            kind,
            quantity,
            label
        )

        if claim is None:
            await channel.delete(
                reason="redemption failed"
            )

            await it.followup.send(
                "balance moved while u blinked 💔",
                ephemeral=True
            )
            return

        detail=(
            f"reward • {emoji} "
            f"**{quantity:,}× {label}**"
        )

        if kind=="steam_game":
            detail+=(
                "\\nprovide your username and the games "
                "you want • maximum $15 each"
            )

        try:
            await channel.edit(
                name=f"redeem-{claim}",
                topic=(
                    f"claim:{claim} • "
                    f"user:{it.user.id} • "
                    f"kind:{kind}"
                )
            )

        except discord.HTTPException:
            pass

        receipt=await channel.send(
            f"🎟️ **redemption #{claim}**\\n"
            f"redeemer • {it.user.mention} "
            f"(`{it.user.id}`)\\n"
            f"{detail}\\n\\n"
            f"{mention(handler_id)}",
            view=RedeemView(
                self.bot
            )
        )

        try:
            await receipt.pin(
                reason="redemption receipt"
            )

        except discord.HTTPException:
            pass

        await it.followup.send(
            f"ticket ⊹ {channel.mention}\\n"
            f"claim #{claim} • "
            f"**{quantity:,}× {label}**",
            ephemeral=True
        )

    @app_commands.command(
        name="redeem",
        description="open the redeem"
    )
    @app_commands.guild_only()
    async def redeem(
        self,
        it:discord.Interaction
    ):
        game.touch(
            it.user.id
        )

        items,rings=buildshop(
            it.guild.id,
            it.user.id
        )

        if not items:
            await it.response.send_message(
                "nothing to redeem rn",
                ephemeral=True
            )
            return

        await it.response.send_message(
            embed=shopembed(
                items,
                rings
            ),
            view=RewardShopView(
                self,
                it.user.id,
                items
            ),
            ephemeral=False
        )




async def setup(bot):
    rewardshop.init()
    embedtheme.install()

    bot.add_view(
        RedeemView(
            bot
        )
    )

    await bot.add_cog(
        Redeem(
            bot
        )
    )
