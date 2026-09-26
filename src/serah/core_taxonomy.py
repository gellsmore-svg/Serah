"""The locked core taxonomy. Definitions are an instrument, not a diagnosis."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CoreConcept:
    taxonomy_id: str
    name: str
    family: str
    definition: str
    inclusion: str
    exclusion: str


CORE_CONCEPTS: tuple[CoreConcept, ...] = (
    CoreConcept(
        "emotion.anger",
        "Anger",
        "emotion",
        "A heated sense that something is wrong, unfair, or blocking, often with an impulse to push back.",
        "The user names anger or describes heated opposition, irritation that has become sharp, or fury.",
        "Do not use for calm disagreement, frustration without heat, or an assistant's guess that the user is angry.",
    ),
    CoreConcept(
        "emotion.fear",
        "Fear",
        "emotion",
        "A response to a sensed threat, including wanting to get away from or brace against something.",
        "The user names fear or describes feeling threatened, frightened, or braced against harm.",
        "Do not use for ordinary planning, anxiety about an unnamed hum, or someone else's description of the user.",
    ),
    CoreConcept(
        "emotion.anxiety",
        "Anxiety",
        "emotion",
        "Uneasy anticipation. A restless sense that something unwelcome may happen, without a single clear threat.",
        "The user names anxiety, worry, edginess, or a persistent uneasy hum about what is coming.",
        "Do not use for a specific fright at a present threat, and do not use as a clinical label.",
    ),
    CoreConcept(
        "emotion.sadness",
        "Sadness",
        "emotion",
        "A heavy, downcast feeling around loss, disappointment, or something that matters having gone wrong.",
        "The user names sadness, grief, or a heavy downcast feeling in their own words.",
        "Do not use for calm tiredness or for an assistant's summary of the user's mood.",
    ),
    CoreConcept(
        "emotion.joy",
        "Joy",
        "emotion",
        "A bright, lifted feeling of pleasure or gladness about something present.",
        "The user names joy, delight, or a clearly lifted gladness.",
        "Do not use for polite positivity or for relief that is mainly the ending of strain.",
    ),
    CoreConcept(
        "emotion.love",
        "Love",
        "emotion",
        "Warm attachment, care, or affection toward a person, creature, or relationship.",
        "The user names love, affection, or a warm caring bond in their own words.",
        "Do not use for generic approval of an idea, or for an assistant attributing love to the user.",
    ),
    CoreConcept(
        "emotion.gratitude",
        "Gratitude",
        "emotion",
        "A felt thankfulness for something given, done, or simply present.",
        "The user names gratitude or thanks, or describes being thankful.",
        "Do not use for polite sign-offs that carry no felt thanks.",
    ),
    CoreConcept(
        "emotion.hope",
        "Hope",
        "emotion",
        "A leaning toward a wanted future that still feels possible.",
        "The user names hope or describes a wanted future as genuinely possible.",
        "Do not use for the everyday phrase 'I hope' when it only means 'I would like'.",
    ),
    CoreConcept(
        "emotion.shame",
        "Shame",
        "emotion",
        "A painful sense of being exposed, small, or unworthy in one's own or someone else's eyes.",
        "The user names shame or describes wanting to hide because of who they feel they are.",
        "Do not use for guilt about a specific act, and do not use as a clinical formulation.",
    ),
    CoreConcept(
        "emotion.guilt",
        "Guilt",
        "emotion",
        "A troubled sense of having done, or failed to do, something one holds oneself responsible for.",
        "The user names guilt or describes responsibility for a specific act or omission.",
        "Do not use for shame about the self as a whole, or for another person's accusation alone.",
    ),
    CoreConcept(
        "emotion.frustration",
        "Frustration",
        "emotion",
        "Strain at being blocked, repeating effort without movement, or not getting through.",
        "The user names frustration or describes being stuck, fed up, or repeatedly blocked.",
        "Do not use for sharp anger unless the user also describes that heat.",
    ),
    CoreConcept(
        "emotion.loneliness",
        "Loneliness",
        "emotion",
        "A felt lack of companionship or of being met, even if other people are nearby.",
        "The user names loneliness or describes feeling unmet or alone.",
        "Do not use merely because the user was physically by themselves.",
    ),
    CoreConcept(
        "emotion.contentment",
        "Contentment",
        "emotion",
        "A settled, quietly satisfied feeling that things are enough for now.",
        "The user names contentment or a settled enough-ness.",
        "Do not use for the word 'content' meaning the material of a book, message, or page.",
    ),
    CoreConcept(
        "emotion.calm",
        "Calm",
        "emotion",
        "A quiet, unhurried state without strong activation.",
        "The user names calm, peace, or being at ease.",
        "Do not use for numbness, shutdown, or an assistant telling the user to calm down.",
    ),
)

CORE_BY_ID = {item.taxonomy_id: item for item in CORE_CONCEPTS}

RELATION_TYPES = (
    "COMPOSED_OF",
    "ASSOCIATED_WITH",
    "AMPLIFIES",
    "INHIBITS",
    "PRECEDES",
    "FOLLOWS",
    "TRIGGERS",
    "PART_OF",
    "RELATED_TO",
)

OBLIGATION_PRESSURE = CoreConcept(
    "compression.obligation_pressure",
    "Obligation pressure",
    "compression",
    "A recurring coupled pattern in which a felt duty, bodily tightness, urgency, and a pull to resolve the duty arrive together, often easing once the duty is met.",
    "Use when duty, bodily tightness, urgency, and the pull to resolve show up together as one pattern in the user's evidence.",
    "Do not use for a single emotion on its own. Do not use as a medical, personality, or diagnostic label.",
)
