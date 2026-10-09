import re
import sqlite3
import time
from collections import OrderedDict

import discord
from core import database

DEFAULT=0x992D22
DEFAULT_HEX="#992D22"
PRICE=1

COLORS={}
FIXED=set()
FOLLOWUPS=OrderedDict()
INSTALLED=False

RESPONSE_SEND=None
RESPONSE_EDIT=None
INTERACTION_EDIT=None
FOLLOWUP_PROP=None
WEBHOOK_SEND=None


def normalize(value):
    raw=str(
        value
    ).strip().upper()

    if raw.startswith("#"):
        raw=raw[1:]

    if not re.fullmatch(
        r"[0-9A-F]{6}",
        raw
    ):
        raise ValueError(
            "invalid hex color"
        )

    return int(
        raw,
        16
    )


def hexcolor(value):
    return f"#{int(value):06X}"


def init():
    with sqlite3.connect(
        database.FILE,
        timeout=15
    ) as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS embed_themes(
                user_id INTEGER PRIMARY KEY,
                color INTEGER NOT NULL,
                updated_at REAL NOT NULL
            )"""
        )

        rows=con.execute(
            """SELECT user_id,color
            FROM embed_themes"""
        ).fetchall()

    COLORS.clear()

    for user_id,color in rows:
        color=int(
            color
        )

        if (
            0<=color<=0xFFFFFF
            and color!=DEFAULT
        ):
            COLORS[
                int(user_id)
            ]=color


def current(user_id):
    return COLORS.get(
        int(
            user_id
        ),
        DEFAULT
    )


def fixed(embed):
    FIXED.add(
        id(
            embed
        )
    )

    return embed


def apply(embed,user_id):
    if not isinstance(
        embed,
        discord.Embed
    ):
        return embed

    marker=id(
        embed
    )

    if marker in FIXED:
        FIXED.discard(
            marker
        )
        return embed

    colour=embed.colour

    if (
        colour is None
        or int(
            colour.value
        )!=DEFAULT
    ):
        return embed

    chosen=current(
        user_id
    )

    if chosen!=DEFAULT:
        embed.colour=discord.Colour(
            chosen
        )

    return embed


def style(kwargs,user_id):
    embed=kwargs.get(
        "embed"
    )

    if isinstance(
        embed,
        discord.Embed
    ):
        apply(
            embed,
            user_id
        )

    embeds=kwargs.get(
        "embeds"
    )

    if embeds:
        for embed in embeds:
            apply(
                embed,
                user_id
            )


def purchase(
    guild_id,
    user_id,
    color
):
    guild_id=database.walletscope(
        guild_id
    )

    user_id=int(
        user_id
    )

    color=int(
        color
    )

    if not 0<=color<=0xFFFFFF:
        raise ValueError(
            "invalid color"
        )

    with sqlite3.connect(
        database.FILE,
        timeout=15
    ) as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        con.execute(
            """INSERT OR IGNORE INTO wallets(
                guild_id,user_id
            ) VALUES(?,?)""",
            (
                guild_id,
                user_id
            )
        )

        row=con.execute(
            """SELECT rings
            FROM wallets
            WHERE guild_id=?
            AND user_id=?""",
            (
                guild_id,
                user_id
            )
        ).fetchone()

        rings=int(
            row[0]
        )

        if rings<PRICE:
            return {
                "ok":False,
                "reason":"broke",
                "balance":rings
            }

        con.execute(
            """UPDATE wallets
            SET rings=rings-?
            WHERE guild_id=?
            AND user_id=?""",
            (
                PRICE,
                guild_id,
                user_id
            )
        )

        if color==DEFAULT:
            con.execute(
                """DELETE FROM embed_themes
                WHERE user_id=?""",
                (
                    user_id,
                )
            )
        else:
            con.execute(
                """INSERT INTO embed_themes(
                    user_id,
                    color,
                    updated_at
                ) VALUES(?,?,?)
                ON CONFLICT(user_id)
                DO UPDATE SET
                    color=excluded.color,
                    updated_at=excluded.updated_at""",
                (
                    user_id,
                    color,
                    time.time()
                )
            )

        balance=rings-PRICE

    if color==DEFAULT:
        COLORS.pop(
            user_id,
            None
        )
    else:
        COLORS[
            user_id
        ]=color

    return {
        "ok":True,
        "color":color,
        "balance":balance,
        "cost":PRICE
    }


def followupkey(webhook):
    return (
        int(
            webhook.id
        ),
        str(
            webhook.token
            or ""
        )
    )


def remember(webhook,user_id):
    key=followupkey(
        webhook
    )

    FOLLOWUPS[
        key
    ]=int(
        user_id
    )

    FOLLOWUPS.move_to_end(
        key
    )

    while len(
        FOLLOWUPS
    )>2048:
        FOLLOWUPS.popitem(
            last=False
        )


def install():
    global INSTALLED
    global RESPONSE_SEND
    global RESPONSE_EDIT
    global INTERACTION_EDIT
    global FOLLOWUP_PROP
    global WEBHOOK_SEND

    init()

    if INSTALLED:
        return

    RESPONSE_SEND=(
        discord.InteractionResponse.send_message
    )

    RESPONSE_EDIT=(
        discord.InteractionResponse.edit_message
    )

    INTERACTION_EDIT=(
        discord.Interaction.edit_original_response
    )

    FOLLOWUP_PROP=(
        discord.Interaction.followup
    )

    WEBHOOK_SEND=(
        discord.Webhook.send
    )

    async def response_send(
        self,
        *args,
        **kwargs
    ):
        style(
            kwargs,
            self._parent.user.id
        )

        return await RESPONSE_SEND(
            self,
            *args,
            **kwargs
        )

    async def response_edit(
        self,
        *args,
        **kwargs
    ):
        style(
            kwargs,
            self._parent.user.id
        )

        return await RESPONSE_EDIT(
            self,
            *args,
            **kwargs
        )

    async def interaction_edit(
        self,
        *args,
        **kwargs
    ):
        style(
            kwargs,
            self.user.id
        )

        return await INTERACTION_EDIT(
            self,
            *args,
            **kwargs
        )

    def followup(self):
        webhook=FOLLOWUP_PROP.__get__(
            self,
            type(
                self
            )
        )

        remember(
            webhook,
            self.user.id
        )

        return webhook

    async def webhook_send(
        self,
        *args,
        **kwargs
    ):
        user_id=FOLLOWUPS.get(
            followupkey(
                self
            )
        )

        if user_id is not None:
            style(
                kwargs,
                user_id
            )

        return await WEBHOOK_SEND(
            self,
            *args,
            **kwargs
        )

    discord.InteractionResponse.send_message=(
        response_send
    )

    discord.InteractionResponse.edit_message=(
        response_edit
    )

    discord.Interaction.edit_original_response=(
        interaction_edit
    )

    discord.Interaction.followup=property(
        followup
    )

    discord.Webhook.send=webhook_send

    INSTALLED=True

    print(
        "embed themes ✓"
    )
