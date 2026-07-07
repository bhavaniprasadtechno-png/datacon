import re

# Keyword patterns ported verbatim from the prototype
# (project/Datacon.dc.html:1320-1326). Originally a priority cascade picking
# one intent; per the SRS's intent classifier ("assign relevant agents",
# plural, Fig. 2's per-agent loop) every matching agent now fires, in the
# prototype's priority order. Questions matching nothing still fall through
# to descriptive alone — the PRD's specified conservative default.
_PREDICTIVE = re.compile(r"forecast|predict|next quarter|next two|projection|will be|expect", re.I)
_DIAGNOSTIC = re.compile(r"why|cause|spike|reason|driv|because|root", re.I)
_PRESCRIPTIVE = re.compile(r"reduce|should|recommend|how do we|improve|cut |lower |action|fix", re.I)


def route(text: str) -> list[str]:
    intents = []
    if _PREDICTIVE.search(text):
        intents.append("predictive")
    if _DIAGNOSTIC.search(text):
        intents.append("diagnostic")
    if _PRESCRIPTIVE.search(text):
        intents.append("prescriptive")
    return intents or ["descriptive"]
