"""Structured outputs for the agents and request bodies for the API."""

from typing import Literal

from pydantic import BaseModel, Field

Category = Literal[
    "suspicious_activity", "vehicle_break_in", "theft", "harassment", "assault",
    "police_activity", "hazard", "medical", "fire", "gathering", "safety_update", "good_news", "other",
]
Severity = Literal["info", "caution", "warning", "urgent"]
Issue = Literal[
    "profiling", "personal_info", "unverified_claim", "prompt_injection", "harassment_or_threat",
    "graphic_detail", "off_topic", "ongoing_emergency", "spam", "self_harm",
]

# ------------------------------------------------------------------- agents


class ModerationResult(BaseModel):
    """Moderator agent: one decision per community post."""
    decision: Literal["publish", "revise", "block", "redirect_911"]
    issues: list[Issue] = Field(default_factory=list, description="Every problem found; empty if none.")
    category: Category
    severity: Severity
    published_text: str = Field(description="What the community sees. publish: the post, lightly cleaned. "
                                            "revise: your rewrite. block / redirect_911: empty string.")
    title: str = Field(description="Calm, factual headline, at most 70 characters.")
    advice: str = Field(description="One practical safety tip for readers, at most 160 characters.")
    note_to_author: str = Field(description="One or two kind sentences telling the author what changed and why. "
                                            "Empty if published unchanged.")


class CorroborationResult(BaseModel):
    """Corroborator agent: is a new report the same incident as an existing one?"""
    same_incident_id: int | None = Field(description="ID of the matching candidate incident, or null if it's new.")
    reason: str = Field(description="One sentence: why it does or doesn't match.")
    title: str = Field(description="Headline for the (merged or new) incident, at most 70 characters.")
    summary: str = Field(description="Calm summary of all reports together, at most 300 characters. "
                                     "Say how many reports there are. No speculation.")
    advice: str = Field(description="One practical safety tip, at most 160 characters.")
    severity: Severity


class ConciergeAction(BaseModel):
    kind: Literal["start_walk", "call", "request_escort", "open_map", "open_resources", "post_alert", "open_shuttle_map",
                  "open_blue_phone_map"]
    label: str = Field(description="Button text, at most 40 characters.")
    origin_place_id: int | None = None
    dest_place_id: int | None = None
    minutes: int | None = Field(default=None, description="start_walk only: minutes until check-in is due.")
    phone: str | None = Field(default=None, description="call only: digits of a number from get_resources.")
    incident_id: int | None = Field(default=None, description="open_map only: incident to focus.")
    category: str | None = Field(default=None, description="post_alert only: suggested alert category, e.g. theft.")


class ConciergeReply(BaseModel):
    """Safety Concierge agent: the chat answer plus optional buttons."""
    reply: str = Field(description="Your answer. Short paragraphs or bullets, at most about 150 words.")
    cited_incident_ids: list[int] = Field(default_factory=list,
                                          description="IDs of incidents from incidents_near that your reply mentions.")
    actions: list[ConciergeAction] = Field(default_factory=list, description="0-3 buttons the user can tap.")


class ResponderBrief(BaseModel):
    """Responder Brief agent: a dispatcher-ready summary after an SOS."""
    headline: str = Field(description="At most 90 characters: what, where.")
    nature: Literal["medical", "violence_or_assault", "being_followed", "theft_or_robbery", "harassment",
                    "fire_or_hazard", "mental_health_crisis", "unknown"]
    threat_present: Literal["yes", "no", "unknown"]
    injuries: str = Field(description="'none reported', 'unknown', or what the caller said.")
    caller: str = Field(description="Name, affiliation, and any medical note the caller chose to share.")
    location: str
    recommended_units: list[Literal["yale_pd", "ems", "fire", "yale_security", "mental_health_clinician"]]
    key_facts: list[str] = Field(description="Only facts stated by the caller or the app. No guesses.")
    ask_caller: list[str] = Field(description="2-4 questions dispatch should ask first.")


# --------------------------------------------------------------- API bodies


class LoginBody(BaseModel):
    netid: str
    password: str
    name: str | None = None
    affiliation: Literal["student", "staff", "faculty"] | None = None


class PostBody(BaseModel):
    text: str
    category: Category
    place_id: int | None = None
    lat: float | None = None
    lng: float | None = None


class ChatBody(BaseModel):
    message: str
    place_id: int | None = None   # where the user says they are (demo location picker)


class SosBody(BaseModel):
    lat: float | None = None
    lng: float | None = None
    place_id: int | None = None


class SosNoteBody(BaseModel):
    note: str


class WalkBody(BaseModel):
    origin_place_id: int | None = None
    origin_lat: float | None = None   # "Current location": the phone's GPS (used only inside the service area)
    origin_lng: float | None = None
    dest_place_id: int
    minutes: int = Field(ge=1, le=120)


class EscortBody(BaseModel):
    from_place_id: int
    to_place_id: int


class CommentBody(BaseModel):
    text: str


class ReactBody(BaseModel):
    kind: Literal["like", "confirm"]


class ProfileBody(BaseModel):
    contacts: list[dict[str, str]] = Field(default_factory=list, max_length=5)
    medical_note: str = Field(default="", max_length=300)
