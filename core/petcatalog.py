from core import emoji as rosieemoji

TIER_ORDER=(
    "base",
    "mid",
    "high",
    "rosarium"
)

NORMAL_SPECIES=(
    "black_cat",
    "white_rabbit",
    "crow",
    "dove",
    "ladybug",
    "bat",
    "swan",
    "rosaerie",
    "komodo_dragon"
)

ROSARIUM_NORMALS=len(
    NORMAL_SPECIES
)

ROSARIUM_GARDEN_LEVEL=1000

# basis points out of 10,000
# 10 / 10,000 = 0.1% per harvested plant
ROSARIUM_BUTTERFLY_BP=10

MORPHS={
    "butterfly":{
        "new":"dove",
        "old_name":"butterfly",
        "old_cost":15000,
        "compensation":7500
    },
    "rose_sprite":{
        "new":"ladybug",
        "old_name":"rose sprite",
        "old_cost":17500,
        "compensation":8750
    },
    "ghost":{
        "new":"bat",
        "old_name":"ghost",
        "old_cost":20000,
        "compensation":10000
    }
}

SPECIES={
    "black_cat":{
        "name":"black cat",
        "emoji":"🐈‍⬛",
        "tier":"base",
        "cost":5000,
        "unlock":0,
        "buff":{
            "label":"lucky paw",
            "effects":{"casino":3},
            "text":"+3% casino profit"
        },
        "moods":(
            "judgmental",
            "plotting",
            "sleepy",
            "offended",
            "watching the wall",
            "pretending not to care"
        ),
        "feed":(
            "ate three bites and walked away",
            "inspected the bowl like it personally failed them",
            "ate without breaking eye contact",
            "accepted the offering. barely"
        ),
        "play":(
            "attacked the string, your hand, then the concept of friendship",
            "chased absolutely nothing across the room",
            "allowed six seconds of playtime",
            "knocked the toy under furniture on purpose"
        ),
        "explore":(
            "came back acting like they pay rent",
            "returned with dirt on exactly one paw",
            "vanished into a hedge and refused to explain",
            "came back smelling faintly like somebody else's house"
        ),
        "finds":(
            "someone else's ribbon",
            "tiny brass bell",
            "half a playing card",
            "warm black feather",
            "key with no lock"
        ),
        "incidents":(
            "has brought another cat home. nobody knows whose cat this is.",
            "is staring at the corner. the corner is losing.",
            "sat directly on something important and will not move."
        )
    },

    "white_rabbit":{
        "name":"white rabbit",
        "emoji":"🐇",
        "tier":"base",
        "cost":5000,
        "unlock":0,
        "buff":{
            "label":"green thumb",
            "effects":{"garden":5},
            "text":"+5% garden profit"
        },
        "moods":(
            "nervous",
            "zooming",
            "hungry again",
            "suspicious of circles",
            "digging",
            "too fast"
        ),
        "feed":(
            "ate like this was a timed event",
            "stuffed their face and immediately asked for more",
            "dragged the food three feet away first",
            "ate the good parts and left evidence"
        ),
        "play":(
            "did three laps around the room for no reason",
            "threw the toy harder than you did",
            "dug at absolutely solid flooring",
            "won a race nobody started"
        ),
        "explore":(
            "returned at a speed that suggests consequences",
            "came back with leaves stuck everywhere",
            "disappeared under something physically too small",
            "returned looking extremely guilty"
        ),
        "finds":(
            "chewed red ribbon",
            "tiny porcelain button",
            "clover with too many leaves",
            "little silver thimble",
            "watch hand stuck at midnight"
        ),
        "incidents":(
            "dug one perfect hole and refuses to elaborate.",
            "has decided the rug is an enemy combatant.",
            "ran past so fast rosie logged it twice."
        )
    },

    "crow":{
        "name":"crow",
        "emoji":"🐦‍⬛",
        "tier":"base",
        "cost":5000,
        "unlock":0,
        "buff":{
            "label":"scavenger",
            "effects":{"pet":10},
            "find_bonus":200,
            "prefer_missing":True,
            "text":"+10% explore roses + better finds"
        },
        "moods":(
            "stealing",
            "observant",
            "shiny-minded",
            "scheming",
            "loud about it",
            "collecting evidence"
        ),
        "feed":(
            "took the food somewhere private like a criminal",
            "ate one piece and hid another for tax purposes",
            "accepted your bribe",
            "made a noise that felt judgmental"
        ),
        "play":(
            "won and then stole the toy",
            "dropped the toy from somewhere unnecessarily high",
            "learned the game and immediately exploited it",
            "ignored the toy and investigated your pockets"
        ),
        "explore":(
            "returned with something that is definitely not theirs",
            "circled once overhead and landed smugly",
            "came back from conducting business",
            "returned with the confidence of someone holding evidence"
        ),
        "finds":(
            "tiny silver key",
            "suspicious button",
            "bent little coin",
            "red glass bead",
            "note with one word missing"
        ),
        "incidents":(
            "has assembled a small pile of objects you swear belonged to you.",
            "keeps saying one noise at the door. nobody is there.",
            "traded something with another crow. rosie was not consulted."
        )
    },

    "dove":{
        "name":"dove",
        "emoji":"🕊️",
        "tier":"mid",
        "cost":15000,
        "unlock":15,
        "buff":{
            "label":"devotion",
            "effects":{"marriage":5},
            "text":"+5% your weekly marriage stipend"
        },
        "moods":(
            "serene",
            "cooing at nothing",
            "watching the window",
            "too peaceful",
            "perched somewhere inconvenient",
            "waiting for somebody"
        ),
        "feed":(
            "pecked delicately at exactly the expensive-looking pieces",
            "accepted breakfast like a tiny diplomat",
            "ate in complete silence",
            "cooed once and considered the transaction complete"
        ),
        "play":(
            "followed the ribbon in one perfect circle",
            "landed on your hand and refused the actual toy",
            "carried the toy somewhere quieter",
            "made the game unexpectedly ceremonial"
        ),
        "explore":(
            "returned with a feather that is somehow not theirs",
            "came back from a very serious errand",
            "circled the roof once before landing",
            "returned smelling faintly like rain"
        ),
        "finds":(
            "soft white feather",
            "tiny olive ribbon",
            "silver leg band",
            "folded love note",
            "smooth moonstone"
        ),
        "incidents":(
            "brought home a second dove that refuses to leave.",
            "delivered a note nobody remembers writing.",
            "has been staring east for twenty minutes."
        )
    },

    "ladybug":{
        "name":"ladybug",
        "emoji":"🐞",
        "tier":"mid",
        "cost":20000,
        "unlock":25,
        "buff":{
            "label":"petal luck",
            "effects":{"pluck":5},
            "text":"+5% pluck roses"
        },
        "moods":(
            "lucky",
            "sunny",
            "wandering",
            "counting spots",
            "leaf-drunk",
            "determined"
        ),
        "feed":(
            "inspected one perfect droplet for several minutes",
            "ate something too small for rosie to identify",
            "wandered across the snack before deciding it counted",
            "accepted a crumb with unreasonable dignity"
        ),
        "play":(
            "climbed your finger like a mountain",
            "walked the entire edge of the toy",
            "flew exactly six inches and called it exercise",
            "hid under a leaf until you admitted defeat"
        ),
        "explore":(
            "returned from the rose patch dusted in pollen",
            "came back riding on a leaf",
            "vanished into the garden and reappeared somewhere impossible",
            "returned with dew on every spot"
        ),
        "finds":(
            "tiny clover",
            "red lacquer bead",
            "perfect seed",
            "dew-bright leaf",
            "pinhead crown"
        ),
        "incidents":(
            "disappeared inside a rose and emerged hours later.",
            "gathered several other ladybugs into what appears to be a meeting.",
            "landed on rosie's nose and has declared ownership."
        )
    },

    "bat":{
        "name":"bat",
        "emoji":"🦇",
        "tier":"mid",
        "cost":25000,
        "unlock":35,
        "buff":{
            "label":"night strike",
            "effects":{"boss":5},
            "text":"+5% boss damage"
        },
        "moods":(
            "upside down",
            "listening",
            "half asleep",
            "awake at the wrong hour",
            "echolocating suspiciously",
            "refusing daylight"
        ),
        "feed":(
            "snatched the food before you finished offering it",
            "ate upside down because apparently that was necessary",
            "accepted the snack and vanished into the curtains",
            "made one tiny approving noise"
        ),
        "play":(
            "dive-bombed the toy with concerning precision",
            "ignored gravity for most of the game",
            "found the toy entirely by sound",
            "won from the ceiling"
        ),
        "explore":(
            "returned just before dawn",
            "came back with attic dust on one wing",
            "vanished into the dark and knew exactly where it was going",
            "returned from somewhere with much better acoustics"
        ),
        "finds":(
            "tiny brass bell",
            "moon-glass shard",
            "old attic key",
            "black ribbon",
            "silver bottle cap"
        ),
        "incidents":(
            "has been hanging from something that absolutely cannot support it.",
            "found an echo in the room that does not belong to this room.",
            "refuses to explain where it goes during daylight."
        )
    },

    "swan":{
        "name":"swan",
        "emoji":"🦢",
        "tier":"high",
        "cost":30000,
        "unlock":40,
        "buff":{
            "label":"serendipity",
            "effects":{
                "casino":2,
                "marriage":4
            },
            "text":"+2% casino profit +4% marriage stipend"
        },
        "moods":(
            "preening",
            "imperious",
            "gliding",
            "waiting for applause",
            "offended by the pond",
            "beautifully hostile"
        ),
        "feed":(
            "accepted the food as though you had passed an audition",
            "ate only after inspecting the presentation",
            "took one bite and looked disappointed in civilization",
            "allowed you to continue feeding it"
        ),
        "play":(
            "turned the game into a performance",
            "ignored the toy and displayed its wings instead",
            "won gracefully and made sure you noticed",
            "glided away before the game was technically over"
        ),
        "explore":(
            "returned looking cleaner than when it left",
            "came back carrying something reflective",
            "disappeared across the water without disturbing it",
            "returned from wherever expensive birds go"
        ),
        "finds":(
            "pearl button",
            "white feather",
            "silver charm",
            "wet ribbon",
            "old wishing coin"
        ),
        "incidents":(
            "attacked its reflection and appears to have won.",
            "has claimed the entire body of water.",
            "accepted food from somebody else and will not discuss the betrayal."
        )
    },

    "rosaerie":{
        "name":"rosaerie",
        "emoji":rosieemoji.ROSE,
        "tier":"high",
        "cost":40000,
        "unlock":45,
        "buff":{
            "label":"full bloom",
            "effects":{
                "garden":4,
                "pluck":4
            },
            "text":"+4% garden profit +4% pluck roses"
        },
        "moods":(
            "blooming",
            "thorn-proud",
            "moonlit",
            "whispering to roses",
            "iridescent",
            "mischievously floral"
        ),
        "feed":(
            "drank one impossible drop of dew",
            "ate a sugar crystal and immediately started glowing",
            "stole pollen from a nearby flower",
            "accepted the offering like an ancient floral tax"
        ),
        "play":(
            "braided a vine around your fingers",
            "disappeared into one rose and emerged from another",
            "threw petals everywhere and blamed the wind",
            "challenged your reflection to a duel"
        ),
        "explore":(
            "returned through a rose that was not there earlier",
            "came back carrying a thorn like a sword",
            "vanished into the hedge in a flash of red",
            "returned trailing petals that never touched the ground"
        ),
        "finds":(
            "rose-gold wing",
            "glass thorn",
            "sealed petal letter",
            "tiny faerie crown",
            "bottle of impossible dew"
        ),
        "incidents":(
            "every rose nearby turned toward it.",
            "left a ring of flowers where it slept.",
            "whispered something to a plant and the plant whispered back."
        )
    },

    "komodo_dragon":{
        "name":"komodo dragon",
        "emoji":"🦎",
        "tier":"high",
        "cost":50000,
        "unlock":50,
        "buff":{
            "label":"apex",
            "effects":{
                "pet":7,
                "boss":4
            },
            "text":"+7% explore roses +4% boss damage"
        },
        "moods":(
            "sunning",
            "ancient",
            "unimpressed",
            "very still",
            "hungry again",
            "territorial"
        ),
        "feed":(
            "swallowed the entire meal before rosie finished logging it",
            "inspected the food once and then made it disappear",
            "accepted your offering with prehistoric indifference",
            "ate enough to make the bowl look theoretical"
        ),
        "play":(
            "dragged the toy away rather than participating",
            "won tug-of-war immediately",
            "stared until you decided that counted as playing",
            "moved once. apparently that was the game"
        ),
        "explore":(
            "returned with mud from somewhere very far away",
            "came back at exactly the same slow pace it left",
            "vanished into the brush despite being enormous",
            "returned carrying evidence of something else's bad decision"
        ),
        "finds":(
            "shed scale",
            "black river stone",
            "rusted expedition tag",
            "sun-bleached shell",
            "tiny dragon charm"
        ),
        "incidents":(
            "blocked the doorway and nobody has negotiated passage.",
            "has been motionless long enough to become furniture.",
            "another lizard approached and immediately reconsidered."
        )
    },

    "butterfly":{
        "name":"butterfly",
        "emoji":"🦋",
        "tier":"rosarium",
        "cost":0,
        "unlock":0,
        "buff":{
            "label":"metamorphosis",
            "effects":{},
            "xp_pct":20,
            "find_bonus":800,
            "prefer_missing":True,
            "text":"+20% pet XP + doubled discovery chance"
        },
        "moods":(
            "between colors",
            "following impossible light",
            "iridescent",
            "becoming",
            "somewhere else",
            "glimmering"
        ),
        "feed":(
            "drank one perfect drop and changed color twice",
            "landed beside the food and somehow made it ceremonial",
            "accepted something too small to see",
            "fed on light for a moment instead"
        ),
        "play":(
            "followed your hand and left an afterimage",
            "vanished mid-circle and finished it somewhere else",
            "landed on your nose like this was always the goal",
            "chased a reflection into the wrong reflection"
        ),
        "explore":(
            "returned from somewhere the map does not contain",
            "followed impossible light and came back brighter",
            "vanished between flowers and returned between seconds",
            "came back carrying something that feels like a memory"
        ),
        "finds":(
            "prismatic wing scale",
            "impossible blue petal",
            "thread of captured light",
            "tiny glass chrysalis",
            "fragment of another season"
        ),
        "incidents":(
            "disappeared for one second and the room changed seasons.",
            "landed on rosie and every red thing nearby became brighter.",
            "cast a shadow shaped like something it has not become yet."
        )
    }
}

BUFFS={
    key:{
        "emoji":info["emoji"],
        **info["buff"]
    }
    for key,info in SPECIES.items()
}

ALIASES={
    info["name"]:key
    for key,info in SPECIES.items()
}

BY_TIER={
    tier:tuple(
        key
        for key,info in SPECIES.items()
        if info["tier"]==tier
    )
    for tier in TIER_ORDER
}
