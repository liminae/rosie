HANDLERS={}
INSTRUCTIONS={}
RECORDERS={}
CLOSERS={}


def reset():
    HANDLERS.clear()
    INSTRUCTIONS.clear()
    RECORDERS.clear()
    CLOSERS.clear()


def normalized(kind):
    kind=str(
        kind
    ).strip().casefold()

    if not kind:
        raise ValueError(
            "fulfillment kind required"
        )

    return kind


def sethandler(
    guild_id,
    kind,
    user_id
):
    guild_id=int(
        guild_id
    )

    user_id=int(
        user_id
    )

    if guild_id<1:
        raise ValueError(
            "invalid guild"
        )

    if user_id<1:
        raise ValueError(
            "invalid handler"
        )

    HANDLERS[
        (
            guild_id,
            normalized(
                kind
            )
        )
    ]=user_id


def handler(
    guild_id,
    kind
):
    if guild_id is None:
        return None

    return HANDLERS.get(
        (
            int(
                guild_id
            ),
            normalized(
                kind
            )
        )
    )


def setinstructions(
    guild_id,
    kind,
    text
):
    text=str(
        text
    ).strip()

    if not text:
        raise ValueError(
            "instructions required"
        )

    INSTRUCTIONS[
        (
            int(
                guild_id
            ),
            normalized(
                kind
            )
        )
    ]=text


def instructions(
    guild_id,
    kind
):
    if guild_id is None:
        return None

    return INSTRUCTIONS.get(
        (
            int(
                guild_id
            ),
            normalized(
                kind
            )
        )
    )


def setrecorder(
    guild_id,
    kind,
    fn
):
    if not callable(
        fn
    ):
        raise ValueError(
            "recorder must be callable"
        )

    RECORDERS[
        (
            int(
                guild_id
            ),
            normalized(
                kind
            )
        )
    ]=fn


def record(
    guild_id,
    kind,
    claim_id,
    user_id,
    item
):
    fn=RECORDERS.get(
        (
            int(
                guild_id
            ),
            normalized(
                kind
            )
        )
    )

    if fn is None:
        return None

    return fn(
        claim_id,
        user_id,
        item
    )


def setcloser(
    guild_id,
    kind,
    fn
):
    if not callable(
        fn
    ):
        raise ValueError(
            "closer must be callable"
        )

    CLOSERS[
        (
            int(
                guild_id
            ),
            normalized(
                kind
            )
        )
    ]=fn


def close(
    guild_id,
    kind,
    claim_id
):
    fn=CLOSERS.get(
        (
            int(
                guild_id
            ),
            normalized(
                kind
            )
        )
    )

    if fn is None:
        return None

    return fn(
        claim_id
    )
