"""
Claude-powered SDA brief generation.

Brief structure mirrors SENTINEL and BioMon:
  SITUATION / ORBITAL ENVIRONMENT / CONJUNCTION ASSESSMENT /
  DEFENSE & OPERATIONAL EXPOSURE / WATCH ITEMS

Claude does prose synthesis and professional framing.
All risk determinations (Pc thresholds, risk levels) come from risk_engine.py
— Claude never makes the risk determination, only articulates it.
"""

import json
from datetime import timezone

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from risk_engine import format_pc, object_type_label


class BriefGenerationError(Exception):
    pass


def _build_prompt(conjunction, track1_alt: float | None, track2_alt: float | None) -> str:
    tca_str = conjunction.tca.strftime("%Y-%m-%d %H:%M UTC")
    pc_str = format_pc(conjunction.pc)
    miss_m = conjunction.miss_distance_km * 1000

    alt1 = f"{track1_alt:.0f} km" if track1_alt else "unknown"
    alt2 = f"{track2_alt:.0f} km" if track2_alt else "unknown"

    return f"""You are an analyst at the Combined Space Operations Center (CSpOC) generating a Space Domain Awareness (SDA) brief for distribution to satellite owner/operators and DoD stakeholders.

CONJUNCTION DATA (from 18th Space Defense Squadron CDM):
- Object 1: {conjunction.sat1_name} (NORAD {conjunction.sat1_norad}) — {object_type_label(conjunction.sat1_type)} — altitude ~{alt1}
- Object 2: {conjunction.sat2_name} (NORAD {conjunction.sat2_norad}) — {object_type_label(conjunction.sat2_type)} — altitude ~{alt2}
- Time of Closest Approach (TCA): {tca_str}
- Miss Distance: {miss_m:.0f} m ({conjunction.miss_distance_km:.3f} km)
- Relative Speed at TCA: {conjunction.relative_speed_km_s:.2f} km/s
- Probability of Collision (Pc): {pc_str}
- Risk Level (Space Force operational standard): {conjunction.risk_level}

Generate a structured SDA brief in exactly this format (use these exact section headers):

SITUATION
2–3 sentences describing what is happening: which objects, when the closest approach occurs, and the headline risk assessment. Plain language — a policy official should understand this paragraph.

ORBITAL ENVIRONMENT
2–3 sentences describing the orbital regime involved (altitude band, inclination, population density, known debris fields if relevant). Explain why this orbital region has the conjunction density it does.

CONJUNCTION ASSESSMENT
4–5 sentences. Explain what the miss distance and Pc numbers mean in operational terms. Contextualize the Pc value against Space Force thresholds (1×10⁻⁵ coordination threshold; 1×10⁻⁴ maneuver threshold). Note the relative speed and what it implies for collision energy if an impact occurred. Note any factors that affect confidence in the Pc estimate.

DEFENSE & OPERATIONAL EXPOSURE
3–4 sentences. Identify which classes of defense or civil assets operate in this orbital regime (ISR, SATCOM, GPS, weather, reconnaissance — be specific to the altitude/inclination). Explain what a collision at this location would mean for the debris environment (Kessler cascade risk, if applicable).

WATCH ITEMS
3–4 bullet points. What stakeholders should monitor over the next 72 hours. What actions are warranted at this risk level per Space Force doctrine. When the next CDM update should be expected. Any recommended coordination.

Write in the professional, spare style of an actual intelligence product. No marketing language. No unnecessary caveats. Be direct about uncertainty where it exists."""


def generate_sda_brief(conjunction, track1_alt: float | None = None,
                       track2_alt: float | None = None) -> dict:
    """
    Generate a structured SDA brief for a conjunction event.
    Returns a dict with section keys matching the brief structure.
    """
    if not ANTHROPIC_API_KEY:
        raise BriefGenerationError("ANTHROPIC_API_KEY not configured")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = _build_prompt(conjunction, track1_alt, track2_alt)

    try:
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
    except BriefGenerationError:
        raise
    except Exception as exc:
        raise BriefGenerationError(f"Claude API error: {exc}") from exc

    return _parse_sections(raw)


def _parse_sections(text: str) -> dict:
    """
    Parse Claude's response into section dict.
    Falls back gracefully if headers are missing.
    """
    headers = [
        "SITUATION",
        "ORBITAL ENVIRONMENT",
        "CONJUNCTION ASSESSMENT",
        "DEFENSE & OPERATIONAL EXPOSURE",
        "WATCH ITEMS",
    ]
    sections: dict[str, str] = {}
    remaining = text

    for i, header in enumerate(headers):
        next_header = headers[i + 1] if i + 1 < len(headers) else None
        start = remaining.find(header)
        if start == -1:
            sections[header] = ""
            continue
        content_start = start + len(header)
        if next_header:
            end = remaining.find(next_header, content_start)
            content = remaining[content_start:end] if end != -1 else remaining[content_start:]
        else:
            content = remaining[content_start:]
        sections[header] = content.strip().lstrip(":").strip()
        remaining = remaining[start:]

    sections["_raw"] = text
    return sections


def brief_to_json(sections: dict) -> str:
    return json.dumps(sections, ensure_ascii=False)


def brief_from_json(brief_json: str) -> dict:
    try:
        return json.loads(brief_json)
    except (json.JSONDecodeError, TypeError):
        return {}
