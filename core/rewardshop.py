import sqlite3
import time

from core import database


def connect():
    con=sqlite3.connect(
        database.FILE,
        timeout=15
    )
    con.row_factory=sqlite3.Row
    return con


def init():
    with connect() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS reward_shop(
                guild_id INTEGER NOT NULL,
                reward_key TEXT NOT NULL,
                label TEXT NOT NULL,
                emoji TEXT NOT NULL DEFAULT '🎁',
                fulfillment TEXT NOT NULL DEFAULT 'claim',
                payload TEXT,
                amount INTEGER NOT NULL DEFAULT 1,
                ring_price INTEGER NOT NULL,
                handler_id INTEGER,
                active INTEGER NOT NULL DEFAULT 1,
                position INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY(guild_id,reward_key)
            )"""
        )

        con.execute(
            """CREATE INDEX IF NOT EXISTS reward_shop_active_idx
            ON reward_shop(guild_id,active,position)"""
        )

        con.execute(
            """CREATE TABLE IF NOT EXISTS reward_claim_meta(
                claim_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                reward_key TEXT,
                label TEXT NOT NULL,
                fulfillment TEXT NOT NULL,
                payload TEXT,
                amount INTEGER NOT NULL,
                ring_cost INTEGER NOT NULL,
                handler_id INTEGER,
                source TEXT NOT NULL,
                source_id INTEGER,
                created_at REAL NOT NULL
            )"""
        )

        con.execute(
            """CREATE INDEX IF NOT EXISTS reward_claim_meta_guild_idx
            ON reward_claim_meta(guild_id,created_at)"""
        )

        con.execute(
            """CREATE INDEX IF NOT EXISTS reward_claim_meta_source_idx
            ON reward_claim_meta(source,source_id)"""
        )

        shopcols={
            row[1]
            for row in con.execute(
                "PRAGMA table_info(reward_shop)"
            )
        }

        if "handler_id" not in shopcols:
            con.execute(
                "ALTER TABLE reward_shop ADD COLUMN handler_id INTEGER"
            )

        metacols={
            row[1]
            for row in con.execute(
                "PRAGMA table_info(reward_claim_meta)"
            )
        }

        if "handler_id" not in metacols:
            con.execute(
                "ALTER TABLE reward_claim_meta ADD COLUMN handler_id INTEGER"
            )


def key(value):
    value=str(
        value
    ).strip().casefold()

    if not value:
        raise ValueError(
            "reward key required"
        )

    if len(value)>64:
        raise ValueError(
            "reward key too long"
        )

    if not all(
        char.isalnum()
        or char in "_-"
        for char in value
    ):
        raise ValueError(
            "reward key must use letters, numbers, _ or -"
        )

    return value


def item(
    guild_id,
    reward_key
):
    with connect() as con:
        return con.execute(
            """SELECT *
            FROM reward_shop
            WHERE guild_id=?
            AND reward_key=?""",
            (
                guild_id,
                key(
                    reward_key
                )
            )
        ).fetchone()


def shop(
    guild_id,
    include_disabled=False
):
    with connect() as con:
        if include_disabled:
            return con.execute(
                """SELECT *
                FROM reward_shop
                WHERE guild_id=?
                ORDER BY
                    active DESC,
                    position,
                    label COLLATE NOCASE,
                    reward_key""",
                (
                    guild_id,
                )
            ).fetchall()

        return con.execute(
            """SELECT *
            FROM reward_shop
            WHERE guild_id=?
            AND active=1
            ORDER BY
                position,
                label COLLATE NOCASE,
                reward_key""",
            (
                guild_id,
            )
        ).fetchall()


def setitem(
    guild_id,
    reward_key,
    label,
    ring_price,
    fulfillment="claim",
    payload=None,
    amount=1,
    emoji="🎁",
    active=True,
    position=0,
    handler_id=None
):
    reward_key=key(
        reward_key
    )

    label=str(
        label
    ).strip()

    fulfillment=str(
        fulfillment
    ).strip().casefold()

    emoji=str(
        emoji or "🎁"
    ).strip()

    if not label:
        raise ValueError(
            "reward label required"
        )

    if not fulfillment:
        raise ValueError(
            "fulfillment required"
        )

    ring_price=int(
        ring_price
    )

    amount=int(
        amount
    )

    position=int(
        position
    )

    handler_id=(
        None
        if handler_id is None
        else int(handler_id)
    )

    if handler_id is not None and handler_id<1:
        raise ValueError(
            "invalid handler"
        )

    if ring_price<1:
        raise ValueError(
            "ring price must be at least 1"
        )

    if amount<1:
        raise ValueError(
            "reward amount must be at least 1"
        )

    payload=(
        None
        if payload is None
        else str(
            payload
        ).strip()
    )

    now=time.time()

    with connect() as con:
        con.execute(
            """INSERT INTO reward_shop(
                guild_id,
                reward_key,
                label,
                emoji,
                fulfillment,
                payload,
                amount,
                ring_price,
                handler_id,
                active,
                position,
                created_at,
                updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(guild_id,reward_key)
            DO UPDATE SET
                label=excluded.label,
                emoji=excluded.emoji,
                fulfillment=excluded.fulfillment,
                payload=excluded.payload,
                amount=excluded.amount,
                ring_price=excluded.ring_price,
                handler_id=excluded.handler_id,
                active=excluded.active,
                position=excluded.position,
                updated_at=excluded.updated_at""",
            (
                guild_id,
                reward_key,
                label,
                emoji,
                fulfillment,
                payload,
                amount,
                ring_price,
                handler_id,
                int(
                    bool(
                        active
                    )
                ),
                position,
                now,
                now
            )
        )

    return item(
        guild_id,
        reward_key
    )


def sethandler(
    guild_id,
    reward_key,
    handler_id
):
    reward_key=key(
        reward_key
    )

    handler_id=(
        None
        if handler_id is None
        else int(handler_id)
    )

    if handler_id is not None and handler_id<1:
        raise ValueError(
            "invalid handler"
        )

    with connect() as con:
        cur=con.execute(
            """UPDATE reward_shop
            SET handler_id=?,
                updated_at=?
            WHERE guild_id=?
            AND reward_key=?""",
            (
                handler_id,
                time.time(),
                int(guild_id),
                reward_key
            )
        )

    return cur.rowcount==1


def deleteitem(
    guild_id,
    reward_key
):
    reward_key=key(
        reward_key
    )

    with connect() as con:
        cur=con.execute(
            """DELETE FROM reward_shop
            WHERE guild_id=?
            AND reward_key=?""",
            (
                int(guild_id),
                reward_key
            )
        )

    return cur.rowcount==1


def setactive(
    guild_id,
    reward_key,
    active
):
    reward_key=key(
        reward_key
    )

    with connect() as con:
        cur=con.execute(
            """UPDATE reward_shop
            SET active=?,
                updated_at=?
            WHERE guild_id=?
            AND reward_key=?""",
            (
                int(
                    bool(
                        active
                    )
                ),
                time.time(),
                guild_id,
                reward_key
            )
        )

    return cur.rowcount==1


def claimmeta(
    claim_id
):
    with connect() as con:
        return con.execute(
            """SELECT *
            FROM reward_claim_meta
            WHERE claim_id=?""",
            (
                claim_id,
            )
        ).fetchone()


def attach(
    claim_id,
    guild_id,
    label,
    fulfillment,
    amount,
    ring_cost,
    source,
    reward_key=None,
    payload=None,
    source_id=None,
    handler_id=None
):
    claim_id=int(
        claim_id
    )

    amount=int(
        amount
    )

    ring_cost=int(
        ring_cost
    )

    if claim_id<1:
        raise ValueError(
            "invalid claim"
        )

    if amount<1:
        raise ValueError(
            "invalid reward amount"
        )

    if ring_cost<0:
        raise ValueError(
            "invalid ring cost"
        )

    label=str(
        label
    ).strip()

    fulfillment=str(
        fulfillment
    ).strip().casefold()

    source=str(
        source
    ).strip().casefold()

    if not label:
        raise ValueError(
            "claim label required"
        )

    if not fulfillment:
        raise ValueError(
            "claim fulfillment required"
        )

    if not source:
        raise ValueError(
            "claim source required"
        )

    reward_key=(
        None
        if reward_key is None
        else key(
            reward_key
        )
    )

    payload=(
        None
        if payload is None
        else str(
            payload
        ).strip()
    )

    handler_id=(
        None
        if handler_id is None
        else int(handler_id)
    )

    with connect() as con:
        exists=con.execute(
            """SELECT 1
            FROM claims
            WHERE id=?""",
            (
                claim_id,
            )
        ).fetchone()

        if exists is None:
            raise ValueError(
                "claim does not exist"
            )

        current=con.execute(
            """SELECT *
            FROM reward_claim_meta
            WHERE claim_id=?""",
            (
                claim_id,
            )
        ).fetchone()

        if current is not None:
            return current

        con.execute(
            """INSERT INTO reward_claim_meta(
                claim_id,
                guild_id,
                reward_key,
                label,
                fulfillment,
                payload,
                amount,
                ring_cost,
                handler_id,
                source,
                source_id,
                created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                claim_id,
                guild_id,
                reward_key,
                label,
                fulfillment,
                payload,
                amount,
                ring_cost,
                handler_id,
                source,
                source_id,
                time.time()
            )
        )

    return claimmeta(
        claim_id
    )

def redeem(
    guild_id,
    reward_key,
    user_id,
    source="shop",
    source_id=None,
    quantity=1
):
    init()

    guild_id=int(
        guild_id
    )

    user_id=int(
        user_id
    )

    quantity=int(
        quantity
    )

    if quantity<1:
        raise ValueError(
            "quantity must be at least 1"
        )

    reward_key=key(
        reward_key
    )

    source=str(
        source
    ).strip().casefold()

    if not source:
        raise ValueError(
            "claim source required"
        )

    if source_id is not None:
        source_id=int(
            source_id
        )

    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        data=con.execute(
            """SELECT *
            FROM reward_shop
            WHERE guild_id=?
            AND reward_key=?
            AND active=1""",
            (
                guild_id,
                reward_key
            )
        ).fetchone()

        if data is None:
            return {
                "ok":False,
                "reason":"unavailable"
            }

        wallet_guild=database.walletscope(
            guild_id
        )

        con.execute(
            """INSERT OR IGNORE INTO wallets(
                guild_id,user_id
            ) VALUES(?,?)""",
            (
                wallet_guild,
                user_id
            )
        )

        rings=int(
            con.execute(
                """SELECT rings
                FROM wallets
                WHERE guild_id=?
                AND user_id=?""",
                (
                    wallet_guild,
                    user_id
                )
            ).fetchone()[0]
        )

        unit_cost=int(
            data[
                "ring_price"
            ]
        )

        cost=(
            unit_cost
            *quantity
        )

        if rings<cost:
            return {
                "ok":False,
                "reason":"broke",
                "cost":cost,
                "unit_cost":unit_cost,
                "quantity":quantity,
                "balance":rings
            }

        unit_amount=int(
            data[
                "amount"
            ]
        )

        total_amount=(
            unit_amount
            *quantity
        )

        label=str(
            data[
                "label"
            ]
        )

        prize=(
            label
            if quantity==1
            else f"{quantity:,}× {label}"
        )

        con.execute(
            """UPDATE wallets
            SET rings=rings-?
            WHERE guild_id=?
            AND user_id=?""",
            (
                cost,
                wallet_guild,
                user_id
            )
        )

        cur=con.execute(
            """INSERT INTO claims(
                user,
                prize,
                time
            ) VALUES(?,?,?)""",
            (
                user_id,
                prize,
                int(
                    time.time()
                )
            )
        )

        claim=cur.lastrowid

        con.execute(
            """INSERT INTO reward_claim_meta(
                claim_id,
                guild_id,
                reward_key,
                label,
                fulfillment,
                payload,
                amount,
                ring_cost,
                source,
                source_id,
                created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                claim,
                guild_id,
                data[
                    "reward_key"
                ],
                label,
                data[
                    "fulfillment"
                ],
                data[
                    "payload"
                ],
                total_amount,
                cost,
                source,
                source_id,
                time.time()
            )
        )

        item=dict(
            data
        )

        item[
            "unit_amount"
        ]=unit_amount

        item[
            "amount"
        ]=total_amount

        item[
            "quantity"
        ]=quantity

        left=(
            rings
            -cost
        )

    return {
        "ok":True,
        "claim":claim,
        "item":item,
        "quantity":quantity,
        "unit_cost":unit_cost,
        "ring_cost":cost,
        "rings_left":left
    }

