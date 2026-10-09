import sqlite3

from core import database


def connect():
    con=sqlite3.connect(database.FILE)
    con.row_factory=sqlite3.Row
    return con


def init():
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS guild_settings(
            guild_id INTEGER PRIMARY KEY,
            drop_channel_id INTEGER,
            drop_ping_role_id INTEGER,
            drop_pings_enabled INTEGER,
            boss_channel_id INTEGER,
            boss_auto_enabled INTEGER,
            reaper_channel_id INTEGER,
            rune_channel_id INTEGER,
            sin_channel_id INTEGER,
            draw_channel_id INTEGER,
            draw_ping_role_id INTEGER,
            draw_pings_enabled INTEGER,
            control_role_id INTEGER,
            control_admins_enabled INTEGER,
            reward_handler_id INTEGER
        )""")

        cols={
            row[1]
            for row in con.execute(
                "PRAGMA table_info(guild_settings)"
            )
        }

        if "boss_channel_id" not in cols:
            con.execute(
                "ALTER TABLE guild_settings "
                "ADD COLUMN boss_channel_id INTEGER"
            )

        if "boss_auto_enabled" not in cols:
            con.execute(
                "ALTER TABLE guild_settings "
                "ADD COLUMN boss_auto_enabled INTEGER"
            )

        if "reaper_channel_id" not in cols:
            con.execute(
                "ALTER TABLE guild_settings "
                "ADD COLUMN reaper_channel_id INTEGER"
            )

        if "rune_channel_id" not in cols:
            con.execute(
                "ALTER TABLE guild_settings "
                "ADD COLUMN rune_channel_id INTEGER"
            )

        if "sin_channel_id" not in cols:
            con.execute(
                "ALTER TABLE guild_settings "
                "ADD COLUMN sin_channel_id INTEGER"
            )

        if "draw_channel_id" not in cols:
            con.execute(
                "ALTER TABLE guild_settings "
                "ADD COLUMN draw_channel_id INTEGER"
            )

        if "draw_ping_role_id" not in cols:
            con.execute(
                "ALTER TABLE guild_settings "
                "ADD COLUMN draw_ping_role_id INTEGER"
            )

        if "draw_pings_enabled" not in cols:
            con.execute(
                "ALTER TABLE guild_settings "
                "ADD COLUMN draw_pings_enabled INTEGER"
            )

        if "control_role_id" not in cols:
            con.execute(
                "ALTER TABLE guild_settings "
                "ADD COLUMN control_role_id INTEGER"
            )

        if "control_admins_enabled" not in cols:
            con.execute(
                "ALTER TABLE guild_settings "
                "ADD COLUMN control_admins_enabled INTEGER"
            )

        if "reward_handler_id" not in cols:
            con.execute(
                "ALTER TABLE guild_settings "
                "ADD COLUMN reward_handler_id INTEGER"
            )


def get(guild_id):
    if guild_id is None:
        return None
    with connect() as con:
        found=con.execute(
            "SELECT * FROM guild_settings WHERE guild_id=?",
            (guild_id,)
        ).fetchone()
    return dict(found) if found else None


def drops(guild_id):
    found=get(guild_id)
    if found is not None:
        return found
    return {
        "guild_id":guild_id,
        "drop_channel_id":None,
        "drop_ping_role_id":None,
        "drop_pings_enabled":None
    }


def setdrops(guild_id,channel_id=None,ping_role_id=None,pings=None):
    current=drops(guild_id)
    if channel_id is not None:
        current["drop_channel_id"]=channel_id
    if ping_role_id is not None:
        current["drop_ping_role_id"]=ping_role_id
    if pings is not None:
        current["drop_pings_enabled"]=int(pings)
    with connect() as con:
        con.execute(
            """INSERT INTO guild_settings(
                guild_id,drop_channel_id,drop_ping_role_id,drop_pings_enabled
            ) VALUES(?,?,?,?)
            ON CONFLICT(guild_id) DO UPDATE SET
                drop_channel_id=excluded.drop_channel_id,
                drop_ping_role_id=excluded.drop_ping_role_id,
                drop_pings_enabled=excluded.drop_pings_enabled""",
            (
                guild_id,
                current["drop_channel_id"],
                current["drop_ping_role_id"],
                current["drop_pings_enabled"]
            )
        )
    return drops(guild_id)

def boss(guild_id):
    found=get(guild_id)

    if found is not None:
        return found

    return {
        "guild_id":guild_id,
        "boss_channel_id":None,
        "boss_auto_enabled":None
    }


def setboss(guild_id,channel_id=None,automatic=None):
    current=boss(guild_id)

    if channel_id is not None:
        current["boss_channel_id"]=channel_id

    if automatic is not None:
        current["boss_auto_enabled"]=int(automatic)

    with connect() as con:
        con.execute(
            "INSERT OR IGNORE INTO guild_settings(guild_id) VALUES(?)",
            (guild_id,)
        )

        con.execute(
            """UPDATE guild_settings
            SET boss_channel_id=?,
                boss_auto_enabled=?
            WHERE guild_id=?""",
            (
                current["boss_channel_id"],
                current["boss_auto_enabled"],
                guild_id
            )
        )

    return boss(guild_id)

def reaper(guild_id):
    found=get(guild_id)

    if found is not None:
        return found

    return {
        "guild_id":guild_id,
        "reaper_channel_id":None
    }


def setreaper(guild_id,channel_id):
    with connect() as con:
        con.execute(
            "INSERT OR IGNORE INTO guild_settings(guild_id) VALUES(?)",
            (guild_id,)
        )

        con.execute(
            """UPDATE guild_settings
            SET reaper_channel_id=?
            WHERE guild_id=?""",
            (
                channel_id,
                guild_id
            )
        )

    return reaper(guild_id)

def rune(guild_id):
    found=get(guild_id)

    if found is not None:
        return found

    return {
        "guild_id":guild_id,
        "rune_channel_id":None
    }


def setrune(guild_id,channel_id):
    with connect() as con:
        con.execute(
            "INSERT OR IGNORE INTO guild_settings(guild_id) VALUES(?)",
            (guild_id,)
        )

        con.execute(
            """UPDATE guild_settings
            SET rune_channel_id=?
            WHERE guild_id=?""",
            (
                channel_id,
                guild_id
            )
        )

    return rune(guild_id)

def sin(guild_id):
    found=get(guild_id)

    if found is not None:
        return found

    return {
        "guild_id":guild_id,
        "sin_channel_id":None
    }


def setsin(guild_id,channel_id):
    with connect() as con:
        con.execute(
            "INSERT OR IGNORE INTO guild_settings(guild_id) VALUES(?)",
            (guild_id,)
        )

        con.execute(
            """UPDATE guild_settings
            SET sin_channel_id=?
            WHERE guild_id=?""",
            (
                channel_id,
                guild_id
            )
        )

    return sin(guild_id)

def draw(guild_id):
    found=get(guild_id)

    if found is not None:
        return found

    return {
        "guild_id":guild_id,
        "draw_channel_id":None,
        "draw_ping_role_id":None,
        "draw_pings_enabled":None
    }


def setdraw(
    guild_id,
    channel_id=None,
    ping_role_id=None,
    pings=None
):
    current=draw(
        guild_id
    )

    if channel_id is not None:
        current["draw_channel_id"]=channel_id

    if ping_role_id is not None:
        current["draw_ping_role_id"]=ping_role_id

    if pings is not None:
        current["draw_pings_enabled"]=int(
            pings
        )

    with connect() as con:
        con.execute(
            "INSERT OR IGNORE INTO guild_settings(guild_id) VALUES(?)",
            (
                guild_id,
            )
        )

        con.execute(
            """UPDATE guild_settings
            SET draw_channel_id=?,
                draw_ping_role_id=?,
                draw_pings_enabled=?
            WHERE guild_id=?""",
            (
                current["draw_channel_id"],
                current["draw_ping_role_id"],
                current["draw_pings_enabled"],
                guild_id
            )
        )

    return draw(
        guild_id
    )


def adminaccess(guild_id):
    found=get(guild_id)

    return bool(
        found
        and found.get(
            "control_admins_enabled"
        )
    )


def setadminaccess(guild_id,enabled):
    with connect() as con:
        con.execute(
            "INSERT OR IGNORE INTO guild_settings(guild_id) VALUES(?)",
            (
                guild_id,
            )
        )

        con.execute(
            """UPDATE guild_settings
            SET control_admins_enabled=?
            WHERE guild_id=?""",
            (
                int(bool(enabled)),
                guild_id
            )
        )

    return adminaccess(
        guild_id
    )


def controlrole(guild_id):
    found=get(guild_id)
    return (
        found.get("control_role_id")
        if found
        else None
    )


def setcontrolrole(guild_id,role_id):
    role_id=(
        None
        if role_id is None
        else int(role_id)
    )

    with connect() as con:
        con.execute(
            "INSERT OR IGNORE INTO guild_settings(guild_id) VALUES(?)",
            (
                guild_id,
            )
        )

        con.execute(
            """UPDATE guild_settings
            SET control_role_id=?
            WHERE guild_id=?""",
            (
                role_id,
                guild_id
            )
        )

    return controlrole(guild_id)


def rewardhandler(guild_id):
    found=get(guild_id)
    return (
        found.get("reward_handler_id")
        if found
        else None
    )


def setrewardhandler(guild_id,user_id):
    user_id=(
        None
        if user_id is None
        else int(user_id)
    )

    with connect() as con:
        con.execute(
            "INSERT OR IGNORE INTO guild_settings(guild_id) VALUES(?)",
            (
                guild_id,
            )
        )

        con.execute(
            """UPDATE guild_settings
            SET reward_handler_id=?
            WHERE guild_id=?""",
            (
                user_id,
                guild_id
            )
        )

    return rewardhandler(guild_id)


def rows():
    with connect() as con:
        return [
            dict(row)
            for row in con.execute(
                "SELECT * FROM guild_settings"
            ).fetchall()
        ]

_COMMAND_CHANNELS_READY=False


def _commandchannelsinit():
    global _COMMAND_CHANNELS_READY

    if _COMMAND_CHANNELS_READY:
        return

    with connect() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS guild_command_channels(
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                PRIMARY KEY(guild_id,channel_id)
            )"""
        )

    _COMMAND_CHANNELS_READY=True


def commandchannels(
    guild_id
):
    _commandchannelsinit()

    with connect() as con:
        rows=con.execute(
            """SELECT channel_id
            FROM guild_command_channels
            WHERE guild_id=?
            ORDER BY channel_id""",
            (
                int(
                    guild_id
                ),
            )
        ).fetchall()

    return [
        int(
            row[
                "channel_id"
            ]
        )
        for row
        in rows
    ]


def setcommandchannels(
    guild_id,
    channel_ids
):
    guild_id=int(
        guild_id
    )

    channel_ids=sorted(
        {
            int(
                channel_id
            )
            for channel_id
            in channel_ids
            if channel_id
        }
    )

    if len(
        channel_ids
    )>25:
        raise ValueError(
            "too many channels"
        )

    _commandchannelsinit()

    with connect() as con:
        con.execute(
            "BEGIN IMMEDIATE"
        )

        con.execute(
            """DELETE FROM guild_command_channels
            WHERE guild_id=?""",
            (
                guild_id,
            )
        )

        con.executemany(
            """INSERT INTO guild_command_channels(
                guild_id,
                channel_id
            ) VALUES(?,?)""",
            [
                (
                    guild_id,
                    channel_id
                )
                for channel_id
                in channel_ids
            ]
        )

    return commandchannels(
        guild_id
    )


def commandchannelallowed(
    guild_id,
    channel_id,
    parent_id=None
):
    allowed=set(
        commandchannels(
            guild_id
        )
    )

    if not allowed:
        return True

    current={
        int(
            value
        )
        for value
        in (
            channel_id,
            parent_id
        )
        if value is not None
    }

    return bool(
        current
        &allowed
    )

