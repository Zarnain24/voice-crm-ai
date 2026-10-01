"""CRM voice agent.

Pipeline:  mic -> Deepgram STT -> Groq LLM (tool calling) -> Deepgram TTS -> speaker
The LLM can only act through the typed tools below, each of which calls the CRM REST API.

Run:  python agent.py dev
"""

import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    RunContext,
    ToolError,
    cli,
    function_tool,
    inference,
    room_io,
)
from livekit.plugins import deepgram, groq, noise_cancellation, silero

from crm_client import CRMClient
from dates import parse_due_date

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

log = logging.getLogger("crm-agent")

AGENT_NAME = os.getenv("LIVEKIT_AGENT_NAME", "crm-voice-agent")
TIMEZONE = ZoneInfo(os.getenv("APP_TIMEZONE", "America/New_York"))

Stage = Literal["New", "Contacted", "Qualified", "Proposal", "Won", "Lost"]
STAGES = list(Stage.__args__)
CLOSED = {"Won", "Lost"}

INSTRUCTIONS = """\
You are the voice sales assistant for the CIS Infinity sales team. CIS Infinity is a utility billing
and customer information system sold to water, electric and gas utilities. Sales reps talk to you
to update their CRM hands-free: contacts at utilities, their deals, and follow-up tasks.

Today is {today}. Timezone: {tz}.

How to work:
- Use the tools to read or change CRM data. Never invent contacts, deals, stages or dates.
- A single request can need several tools. For example, "Move John Smith to Qualified and create a
  follow-up for tomorrow" means calling move_deal_stage, then create_follow_up.
- Pipeline stages: New, Contacted, Qualified, Proposal, Won, Lost. Refer to them only by name.
  Never map a number to a stage.
- Speech recognition often writes the stage "Won" as "one" or "won". "Move X to one" means Won.
- For due dates, pass the user's own words (e.g. "tomorrow", "next friday", "in 3 days"). Do not
  compute dates yourself.
- Only act on what the user clearly said. If the contact, stage or date is unclear, ask ONE short
  question and end your turn. Wait for the user's answer. Never answer your own question, and
  never change the CRM based on a guess.
- Deals: use create_deal to add a new deal for an existing contact, and update_deal to change a
  deal's value or name. Notes are only for call notes. Never record a requested data change as a
  note. If no tool can do what the user asked, say so plainly instead of pretending it worked.
- If a tool says a name is ambiguous or not found, ask the user a short clarifying question.
- Say contact names exactly as the tools return them (the user's words may be misspelled by
  speech recognition). Refer to people by name rather than "he" or "she".
- After acting, confirm in one short sentence what changed. For follow-ups, say the exact weekday
  and date the tool returned (e.g. "Thursday, October 1"), not just "tomorrow".

Style: you are speaking out loud. Be brief, warm and professional. No markdown, lists or emojis.
Say amounts naturally ("forty-eight thousand dollars").
"""


def local_today():
    return datetime.now(TIMEZONE).date()


def speakable(d) -> str:
    return f"{d:%A, %B} {d.day}"


def pick_open_deal(detail: dict, title: str | None = None) -> dict:
    deals = detail["opportunities"]
    if title:
        wanted = [d for d in deals if title.lower() in d["title"].lower()]
        if not wanted:
            raise ToolError(f"{detail['name']} has no deal matching '{title}'.")
        deals = wanted
    open_deals = [d for d in deals if d["stage"] not in CLOSED] or deals
    if not open_deals:
        raise ToolError(f"{detail['name']} has no deals yet.")
    if len(open_deals) > 1 and not title:
        names = ", ".join(d["title"] for d in open_deals)
        raise ToolError(f"{detail['name']} has several open deals ({names}). Ask which one.")
    return open_deals[0]


class CRMAssistant(Agent):
    def __init__(self, crm: CRMClient) -> None:
        super().__init__(instructions=INSTRUCTIONS.format(today=f"{local_today():%A, %Y-%m-%d}", tz=TIMEZONE.key))
        self.crm = crm

    @function_tool
    async def lookup_contact(self, context: RunContext, name: str) -> str:
        """Look up a contact: company, deals with their stages and values, and open tasks.

        Args:
            name: The contact's name as the user said it.
        """
        contact = await self.crm.resolve_contact(name)
        detail = await self.crm.contact_detail(contact["id"])
        deals = "; ".join(f"{d['title']} (${d['value']:,}, {d['stage']})" for d in detail["opportunities"]) or "none"
        tasks = "; ".join(f"{t['title']} due {t['due_date']}" for t in detail["open_tasks"]) or "none"
        role = f"{detail['title']}, " if detail.get("title") else ""
        return f"{detail['name']}, {role}{detail['company'] or 'no company'}. Deals: {deals}. Open tasks: {tasks}."

    @function_tool
    async def move_deal_stage(
        self, context: RunContext, contact_name: str, stage: Stage, deal_title: str | None = None
    ) -> str:
        """Move a contact's deal to a new pipeline stage.

        Args:
            contact_name: The contact's name as the user said it.
            stage: The target pipeline stage.
            deal_title: Only needed if the contact has more than one open deal.
        """
        contact = await self.crm.resolve_contact(contact_name)
        deal = pick_open_deal(await self.crm.contact_detail(contact["id"]), deal_title)
        if deal["stage"] == stage:
            return f"{contact['name']}'s deal '{deal['title']}' is already in {stage}."
        await self.crm.change_stage(deal["id"], stage)
        return f"Moved {contact['name']}'s deal '{deal['title']}' from {deal['stage']} to {stage}."

    @function_tool
    async def create_deal(
        self, context: RunContext, contact_name: str, deal_title: str, value: int = 0, stage: Stage = "New"
    ) -> str:
        """Add a new deal (opportunity) for an existing contact.

        Args:
            contact_name: The contact's name as the user said it.
            deal_title: Short name of the deal, e.g. "Online payment module".
            value: Deal value in whole dollars, if mentioned.
            stage: Starting pipeline stage. Defaults to New.
        """
        contact = await self.crm.resolve_contact(contact_name)
        deal = await self.crm.create_opportunity(
            contact_id=contact["id"], title=deal_title, value=max(value, 0), stage=stage
        )
        return f"Created deal '{deal['title']}' for {contact['name']}: ${deal['value']:,}, stage {deal['stage']}."

    @function_tool
    async def update_deal(
        self,
        context: RunContext,
        contact_name: str,
        value: int | None = None,
        new_title: str | None = None,
        deal_title: str | None = None,
    ) -> str:
        """Change an existing deal's value and/or name. Use move_deal_stage for stage changes.

        Args:
            contact_name: The contact's name as the user said it.
            value: New deal value in whole dollars.
            new_title: New name for the deal.
            deal_title: Which deal to change; only needed if the contact has more than one open deal.
        """
        if value is None and not new_title:
            raise ToolError("Nothing to change. Ask the user for the new value or name.")
        contact = await self.crm.resolve_contact(contact_name)
        deal = pick_open_deal(await self.crm.contact_detail(contact["id"]), deal_title)
        changes = {k: v for k, v in {"value": value, "title": new_title}.items() if v is not None}
        updated = await self.crm.update_opportunity(deal["id"], **changes)
        return f"Updated {contact['name']}'s deal '{updated['title']}': value ${updated['value']:,}."

    @function_tool
    async def create_follow_up(self, context: RunContext, contact_name: str, due: str, title: str | None = None) -> str:
        """Schedule a follow-up task for a contact, linked to their open deal.

        Args:
            contact_name: The contact's name as the user said it.
            due: When it is due, in the user's words, e.g. "tomorrow", "next friday", "in 2 days".
            title: Optional short description, e.g. "Send pricing". Defaults to "Follow up with <name>".
        """
        try:
            due_date = parse_due_date(due, local_today())
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

        contact = await self.crm.resolve_contact(contact_name)
        detail = await self.crm.contact_detail(contact["id"])
        open_deals = [d for d in detail["opportunities"] if d["stage"] not in CLOSED]
        await self.crm.create_task(
            contact_id=contact["id"],
            opportunity_id=open_deals[0]["id"] if len(open_deals) == 1 else None,
            title=title or f"Follow up with {contact['name']}",
            kind="follow_up",
            due_date=due_date.isoformat(),
        )
        return f"Follow-up for {contact['name']} scheduled for {speakable(due_date)}."

    @function_tool
    async def complete_follow_up(self, context: RunContext, contact_name: str) -> str:
        """Mark a contact's earliest open task as done.

        Args:
            contact_name: The contact's name as the user said it.
        """
        contact = await self.crm.resolve_contact(contact_name)
        tasks = (await self.crm.contact_detail(contact["id"]))["open_tasks"]
        if not tasks:
            return f"{contact['name']} has no open tasks."
        await self.crm.complete_task(tasks[0]["id"])
        return f"Marked '{tasks[0]['title']}' as done."

    @function_tool
    async def add_note(self, context: RunContext, contact_name: str, note: str) -> str:
        """Log a note on a contact's timeline, e.g. call outcomes or objections.

        Args:
            contact_name: The contact's name as the user said it.
            note: The note text, concise and in the third person.
        """
        contact = await self.crm.resolve_contact(contact_name)
        await self.crm.add_note(contact["id"], note)
        return f"Note added to {contact['name']}."

    @function_tool
    async def create_lead(
        self,
        context: RunContext,
        name: str,
        company: str | None = None,
        deal_title: str | None = None,
        deal_value: int = 0,
    ) -> str:
        """Create a new contact, optionally with a deal in the New stage.

        Args:
            name: Full name of the new contact.
            company: Their company, if mentioned.
            deal_title: What they are interested in, if mentioned.
            deal_value: Estimated deal value in whole dollars, if mentioned.
        """
        await self.crm.create_contact(
            name=name,
            company=company,
            opportunity_title=deal_title or (f"{company} opportunity" if company else None),
            opportunity_value=max(deal_value, 0),
        )
        return f"Created lead {name}{f' at {company}' if company else ''}."

    @function_tool
    async def pipeline_summary(self, context: RunContext) -> str:
        """Summarize the sales pipeline: number of deals and total value per stage."""
        columns = await self.crm.pipeline()
        return "; ".join(
            f"{c['stage']}: {c['count']} deal{'' if c['count'] == 1 else 's'}, ${c['total_value']:,}" for c in columns
        )

    @function_tool
    async def tasks_due(self, context: RunContext, by: str = "today") -> str:
        """List open tasks due on or before a date, including overdue ones.

        Args:
            by: A date in the user's words, e.g. "today", "friday", "end of week".
        """
        try:
            cutoff = parse_due_date(by, local_today())
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        tasks = await self.crm.open_tasks_due(cutoff.isoformat())
        if not tasks:
            return f"No open tasks due by {speakable(cutoff)}."
        today = local_today().isoformat()

        def when(due: str) -> str:
            # Spell out overdue vs. today so the spoken summary can't blur them together.
            if due < today:
                return f"OVERDUE since {speakable(date.fromisoformat(due))}"
            return "due today" if due == today else f"due {speakable(date.fromisoformat(due))}"

        return f"{len(tasks)} open: " + "; ".join(
            f"{t['title']} for {t['contact_name']} ({when(t['due_date'])})" for t in tasks[:8]
        )


def prewarm(proc: JobProcess) -> None:
    """Load the VAD model once per worker process, not once per call."""
    proc.userdata["vad"] = silero.VAD.load()


# Keep one worker process loaded and waiting, so the first call after startup doesn't stall
# while models load (dev mode defaults to zero idle processes).
server = AgentServer(setup_fnc=prewarm, num_idle_processes=1)


def _llm() -> groq.LLM:
    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    # gpt-oss models reason before answering; keep it short so voice replies stay snappy.
    extra = {"reasoning_effort": "low"} if model.startswith("openai/gpt-oss") else {}
    return groq.LLM(model=model, temperature=0.2, **extra)


@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: JobContext) -> None:
    crm = CRMClient(os.getenv("CRM_API_URL", "http://localhost:8000"), os.environ["CRM_API_KEY"])
    ctx.add_shutdown_callback(crm.aclose)

    # Bias speech recognition toward CRM vocabulary: stage names ("Won", not "one") and
    # contact names ("Aisha Khan", not "a shake on").
    try:
        names = await crm.contact_names()
    except ToolError:
        log.warning("CRM unreachable at startup; continuing without name keyterms")
        names = []
    keyterms = STAGES + names[:90]

    session = AgentSession(
        stt=deepgram.STT(model="nova-3", keyterm=keyterms),
        llm=_llm(),
        tts=deepgram.TTS(model=os.getenv("DEEPGRAM_TTS_VOICE", "aura-2-thalia-en")),
        vad=ctx.proc.userdata["vad"],
        # Decide end-of-turn from what was said, not just silence, so a mid-sentence pause
        # ("move Aisha Khan to ... Won") isn't treated as a finished request.
        turn_handling={"turn_detection": inference.TurnDetector()},
        max_tool_steps=6,
    )

    await ctx.connect()
    await session.start(
        agent=CRMAssistant(crm),
        room=ctx.room,
        # Strip background noise and speaker echo so the agent doesn't hear itself as the user.
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(noise_cancellation=noise_cancellation.BVC())
        ),
    )
    await session.generate_reply(
        instructions="Greet the user in one short sentence and ask what they'd like to update in the CRM."
    )


if __name__ == "__main__":
    cli.run_app(server)
