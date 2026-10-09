ADMIN_USERS=set()

def haspermission(user,name):
    permissions=getattr(
        user,
        "guild_permissions",
        None
    )

    return bool(
        permissions
        and getattr(
            permissions,
            name,
            False
        )
    )

def reset():
    ADMIN_USERS.clear()

def __getattr__(name):
    if name.endswith("_ID"):
        return 0

    if name.endswith("_WATCH"):
        return {}

    return set()
