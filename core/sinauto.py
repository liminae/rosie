from itertools import product

EPS=1e-9

def gains(picks):
    counts={}

    for number in picks.values():
        counts[number]=(
            counts.get(
                number,
                0
            )
            +1
        )

    return {
        user_id:
            number/counts[number]
        for user_id,number
        in picks.items()
    }

def simulate(
    target,
    picks,
    scores,
    planned
):
    chosen=dict(
        picks
    )

    for user_id,number in planned.items():
        if user_id not in chosen:
            chosen[
                user_id
            ]=number

    nightly=gains(
        chosen
    )

    users=(
        set(scores)
        |set(chosen)
    )

    projected={
        user_id:
            float(
                scores.get(
                    user_id,
                    0
                )
            )
            +nightly.get(
                user_id,
                0
            )
        for user_id in users
    }

    winner=None

    if projected:
        high=max(
            projected.values()
        )

        leaders=[
            user_id
            for user_id,value
            in projected.items()
            if abs(
                value-high
            )<=EPS
        ]

        if (
            len(leaders)==1
            and high>=target
        ):
            winner=leaders[
                0
            ]

    ranks={
        user_id:
            1+sum(
                value
                >projected[
                    user_id
                ]
                +EPS
                for other,value
                in projected.items()
                if other!=user_id
            )
        for user_id in users
    }

    return {
        "gains":nightly,
        "projected":projected,
        "ranks":ranks,
        "winner":winner
    }

def denial(
    baseline,
    result,
    scores,
    external,
    target,
    threshold
):
    raw=0.0
    weighted=0.0
    ahead=0.0

    for user_id in external:
        lost=max(
            0.0,
            baseline.get(
                user_id,
                0.0
            )
            -result[
                "gains"
            ].get(
                user_id,
                0.0
            )
        )

        score=float(
            scores.get(
                user_id,
                0.0
            )
        )

        threat=(
            1.0
            +min(
                1.0,
                max(
                    0.0,
                    score/target
                )
            )
        )

        raw+=lost
        weighted+=(
            lost
            *threat
        )

        if score+EPS>=threshold:
            ahead+=(
                lost
                *threat
            )

    return (
        raw,
        weighted,
        ahead
    )

def racepressure(
    baseline,
    result,
    scores,
    external,
    target,
    reference
):
    projected={
        user_id:
            float(
                scores.get(
                    user_id,
                    0.0
                )
            )
            +baseline[
                "gains"
            ].get(
                user_id,
                0.0
            )
        for user_id in external
    }

    pressure=0.0
    leader_denied=0.0
    threat_denied=0.0

    for user_id in external:
        denied=max(
            0.0,
            baseline[
                "gains"
            ].get(
                user_id,
                0.0
            )
            -result[
                "gains"
            ].get(
                user_id,
                0.0
            )
        )

        if denied<=EPS:
            continue

        score=projected[
            user_id
        ]

        rank=(
            1
            +sum(
                value>score+EPS
                for other,value
                in projected.items()
                if other!=user_id
            )
        )

        progress=min(
            1.0,
            max(
                0.0,
                score/target
            )
        )

        if rank==1:
            weight=(
                .10
                +1.15
                *progress**3
            )
        elif rank==2:
            weight=(
                .05
                +.55
                *progress**3
            )
        elif rank==3:
            weight=(
                .02
                +.25
                *progress**3
            )
        else:
            weight=(
                .05
                *progress**3
            )

        if score>=reference-EPS:
            weight*=1.15
        else:
            weight*=.70

        pressure+=(
            denied
            *weight
        )

        if rank==1:
            leader_denied+=denied

        if score>=target*.75:
            threat_denied+=denied

    return (
        pressure,
        leader_denied,
        threat_denied
    )

def plan(
    max_number,
    target,
    picks,
    scores,
    team
):
    max_number=int(
        max_number
    )

    target=float(
        target
    )

    picks={
        int(user_id):
            int(number)
        for user_id,number
        in picks.items()
    }

    scores={
        int(user_id):
            float(score)
        for user_id,score
        in scores.items()
    }

    team=tuple(
        dict.fromkeys(
            int(user_id)
            for user_id in team
        )
    )

    if len(team) not in (
        1,
        2
    ):
        raise ValueError(
            "team must have 1 or 2 players"
        )

    baseline=simulate(
        target,
        picks,
        scores,
        {}
    )

    baseline_gains=gains(
        picks
    )

    external=[
        user_id
        for user_id in (
            set(scores)
            |set(picks)
        )
        if user_id not in team
    ]

    fixed={
        user_id:
            picks[
                user_id
            ]
        for user_id in team
        if user_id in picks
    }

    free=[
        user_id
        for user_id in team
        if user_id not in fixed
    ]

    combinations=(
        product(
            range(
                1,
                max_number+1
            ),
            repeat=len(
                free
            )
        )
        if free
        else (
            (),
        )
    )

    candidates=[]

    if len(team)==1:
        user_id=team[
            0
        ]

        start=float(
            scores.get(
                user_id,
                0
            )
        )

        for values in combinations:
            choices=dict(
                fixed
            )

            choices.update(
                zip(
                    free,
                    values
                )
            )

            result=simulate(
                target,
                picks,
                scores,
                choices
            )

            score=result[
                "projected"
            ].get(
                user_id,
                start
            )

            rank=result[
                "ranks"
            ].get(
                user_id,
                1
            )

            opponent=max(
                (
                    result[
                        "projected"
                    ].get(
                        other,
                        scores.get(
                            other,
                            0.0
                        )
                    )
                    for other in external
                ),
                default=0.0
            )

            raw,weighted,ahead=denial(
                baseline_gains,
                result,
                scores,
                external,
                target,
                start
            )

            (
                race_pressure,
                leader_denied,
                threat_denied
            )=racepressure(
                baseline,
                result,
                scores,
                external,
                target,
                start
            )

            raw_gap=(
                score-opponent
            )

            strategic_gap=(
                raw_gap
                +race_pressure
            )

            gain=result[
                "gains"
            ].get(
                user_id,
                0.0
            )

            external_win=(
                result[
                    "winner"
                ] is not None
                and result[
                    "winner"
                ]!=user_id
            )

            number=choices[
                user_id
            ]

            key=(
                int(
                    result[
                        "winner"
                    ]==user_id
                ),
                int(
                    not external_win
                ),
                -rank,
                strategic_gap,
                raw_gap,
                leader_denied,
                threat_denied,
                ahead,
                weighted,
                raw,
                gain,
                number
            )

            candidates.append({
                "key":key,
                "choices":choices,
                "actions":{
                    key:value
                    for key,value
                    in choices.items()
                    if key in free
                },
                "gains":
                    result[
                        "gains"
                    ],
                "projected":
                    result[
                        "projected"
                    ],
                "ranks":
                    result[
                        "ranks"
                    ],
                "winner":
                    result[
                        "winner"
                    ],
                "gain":gain,
                "denied":raw,
                "weighted_denied":
                    weighted,
                "denied_ahead":
                    ahead,
                "leader_denied":
                    leader_denied,
                "threat_denied":
                    threat_denied,
                "race_pressure":
                    race_pressure,
                "strategic_gap":
                    strategic_gap,
                "gap":
                    raw_gap
            })

        candidates.sort(
            key=lambda item:
                item[
                    "key"
                ],
            reverse=True
        )

        best=candidates[
            0
        ]

        if best[
            "winner"
        ]==user_id:
            reason="wins tonight"

        elif (
            baseline[
                "winner"
            ] is not None
            and baseline[
                "winner"
            ]!=user_id
            and best[
                "winner"
            ]!=baseline[
                "winner"
            ]
        ):
            reason=(
                "blocks "
                f"<@{baseline['winner']}> "
                "from winning"
            )

        elif best[
            "ranks"
        ].get(
            user_id,
            1
        )==1:
            reason="takes projected 1st"

        elif (
            best[
                "leader_denied"
            ]>EPS
            and best[
                "race_pressure"
            ]>.5
        ):
            reason="pressures the projected leader"

        elif (
            best[
                "threat_denied"
            ]>EPS
            and best[
                "race_pressure"
            ]>.5
        ):
            reason="cuts down a title threat"

        elif best[
            "denied_ahead"
        ]>EPS:
            reason="pressures a leading rival"

        else:
            reason="best point swing"

        return {
            "mode":"solo",
            "team":team,
            "captain":user_id,
            "wing":None,
            "best":best,
            "top":candidates[:3],
            "baseline_winner":
                baseline[
                    "winner"
                ],
            "reason":reason
        }

    order={
        user_id:index
        for index,user_id
        in enumerate(
            team
        )
    }

    captain=max(
        team,
        key=lambda user_id:(
            float(
                scores.get(
                    user_id,
                    0
                )
            ),
            -order[
                user_id
            ]
        )
    )

    wing=next(
        user_id
        for user_id in team
        if user_id!=captain
    )

    captain_start=float(
        scores.get(
            captain,
            0
        )
    )

    for values in combinations:
        choices=dict(
            fixed
        )

        choices.update(
            zip(
                free,
                values
            )
        )

        result=simulate(
            target,
            picks,
            scores,
            choices
        )

        captain_score=result[
            "projected"
        ].get(
            captain,
            captain_start
        )

        wing_score=result[
            "projected"
        ].get(
            wing,
            float(
                scores.get(
                    wing,
                    0
                )
            )
        )

        captain_rank=result[
            "ranks"
        ].get(
            captain,
            1
        )

        wing_rank=result[
            "ranks"
        ].get(
            wing,
            1
        )

        external_best=max(
            (
                result[
                    "projected"
                ].get(
                    other,
                    scores.get(
                        other,
                        0.0
                    )
                )
                for other in external
            ),
            default=0.0
        )

        raw,weighted,ahead=denial(
            baseline_gains,
            result,
            scores,
            external,
            target,
            captain_start
        )

        (
            race_pressure,
            leader_denied,
            threat_denied
        )=racepressure(
            baseline,
            result,
            scores,
            external,
            target,
            captain_start
        )

        captain_gap=(
            captain_score
            -external_best
        )

        strategic_gap=(
            captain_gap
            +race_pressure
        )

        team_gain=(
            result[
                "gains"
            ].get(
                captain,
                0.0
            )
            +result[
                "gains"
            ].get(
                wing,
                0.0
            )
        )

        winner=result[
            "winner"
        ]

        team_win=(
            winner in team
            if winner is not None
            else False
        )

        external_win=(
            winner is not None
            and winner not in team
        )

        collision=int(
            choices[
                captain
            ]
            ==choices[
                wing
            ]
        )

        key=(
            int(
                team_win
            ),
            int(
                not external_win
            ),
            int(
                winner==captain
            ),
            -captain_rank,
            strategic_gap,
            captain_gap,
            leader_denied,
            threat_denied,
            -wing_rank,
            wing_score
                -external_best,
            ahead,
            weighted,
            raw,
            team_gain,
            -collision,
            result[
                "gains"
            ].get(
                captain,
                0.0
            ),
            result[
                "gains"
            ].get(
                wing,
                0.0
            ),
            choices[
                captain
            ],
            choices[
                wing
            ]
        )

        candidates.append({
            "key":key,
            "choices":choices,
            "actions":{
                key:value
                for key,value
                in choices.items()
                if key in free
            },
            "gains":
                result[
                    "gains"
                ],
            "projected":
                result[
                    "projected"
                ],
            "ranks":
                result[
                    "ranks"
                ],
            "winner":winner,
            "denied":raw,
            "weighted_denied":
                weighted,
            "denied_ahead":
                ahead,
            "leader_denied":
                leader_denied,
            "threat_denied":
                threat_denied,
            "race_pressure":
                race_pressure,
            "strategic_gap":
                strategic_gap,
            "team_gain":
                team_gain,
            "gap":
                captain_gap,
            "collision":
                collision
        })

    candidates.sort(
        key=lambda item:
            item[
                "key"
            ],
        reverse=True
    )

    best=candidates[
        0
    ]

    if best[
        "winner"
    ] in team:
        reason=(
            "wins tonight for "
            f"<@{best['winner']}>"
        )

    elif (
        baseline[
            "winner"
        ] is not None
        and baseline[
            "winner"
        ] not in team
        and best[
            "winner"
        ]!=baseline[
            "winner"
        ]
    ):
        reason=(
            "blocks "
            f"<@{baseline['winner']}> "
            "from winning"
        )

    elif best[
        "ranks"
    ].get(
        captain,
        1
    )==1:
        reason=(
            f"puts <@{captain}> "
            "in projected 1st"
        )

    elif (
        best[
            "leader_denied"
        ]>EPS
        and best[
            "race_pressure"
        ]>.5
    ):
        reason="team pressures the projected leader"

    elif (
        best[
            "threat_denied"
        ]>EPS
        and best[
            "race_pressure"
        ]>.5
    ):
        reason="team cuts down a title threat"

    elif best[
        "denied_ahead"
    ]>EPS:
        reason="wing pressures a leading rival"

    else:
        reason="best team point swing"

    return {
        "mode":"twin",
        "team":team,
        "captain":captain,
        "wing":wing,
        "best":best,
        "top":candidates[:3],
        "baseline_winner":
            baseline[
                "winner"
            ],
        "reason":reason
    }
