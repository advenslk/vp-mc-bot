"""Central HelzerX custom emoji registry.

Keep every Discord custom emoji in one place. Command/UI modules should never
hard-code emoji IDs directly.
"""

EMOJI = {
    "brand": "<:emoji_11:1553730794906845255>",
    "ram": "<:Ram:1553733475910287402>",
    "cpu": "<:cpu:1553734510313742366>",
    "disk": "<:Disk:1553733604411187220>",
    "money": "<:Money:1553733543153369158>",
    "currency": "<:Currency:1553814442498592851>",
    "minecraft": "<:mc_infra:1553747296900874372>",
    "ping": "<:Ping:1553748197447434240>",
    "singapore": "<:singapore:1553748751309344798>",
    "india": "<:india:1553748866040594512>",
    "germany": "<:germany:1553749530674069514>",
    "hong_kong": "<:Hong_kong:1553751514336460951>",
    "usa": "<:usa:1553751607244627978>",
    "vietnam": "<:Vietnam:1553751734684360825>",
    "australia": "<:Australia:1553751677281112174>",
    "gift": "<:Gift:1553930031313453137>",
    "code": "<:Code:1554049293977919498>",
    "node": "<:Node:1553765934504616038>",
    "invites": "<:Inv:1554048302293721110>",
    "support": "<:Support:1554048214062080111>",
    "star": "<:Star:1554048856122204241>",
    "warning": "<:Warnning:1553754657351012362>",
}

def e(name: str, fallback: str = "") -> str:
    return EMOJI.get(name, fallback)
