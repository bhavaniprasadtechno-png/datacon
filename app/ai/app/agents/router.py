import re

# Keyword patterns ported from the prototype. Questions outside Datacon's
# analytics/business domain now route to a general assistant instead of
# incorrectly falling through to the descriptive revenue summary.
_PREDICTIVE = re.compile(r"forecast|predict|next quarter|next two|projection|will be|expect", re.I)
_DIAGNOSTIC = re.compile(r"why|cause|spike|reason|driv|because|root", re.I)
_PRESCRIPTIVE = re.compile(r"reduce|should|recommend|how do we|improve|cut |lower |action|fix", re.I)
_BUSINESS_CONTEXT = re.compile(
    r"revenue|sales|region|quarter|forecast|growth|churn|customer|account|ticket|support|billing|incident|"
    r"dashboard|metric|kpi|connector|dataset|table|document|upload|insight|trend|anomal|role|permission|user",
    re.I,
)


def route(text: str) -> list[str]:
    if not text.strip():
        return ["descriptive"]

    if not _BUSINESS_CONTEXT.search(text):
        return ["general"]

    intents = []
    if _PREDICTIVE.search(text):
        intents.append("predictive")
    if _DIAGNOSTIC.search(text):
        intents.append("diagnostic")
    if _PRESCRIPTIVE.search(text):
        intents.append("prescriptive")
    return intents or ["descriptive"]
