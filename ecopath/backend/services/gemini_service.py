"""
EcoPath — Gemini AI Service
Wraps Gemini 2.0 Flash for both causal reasoning and vision ID.
"""

import base64
import json
import logging
from typing import Any, AsyncIterator, Optional

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from config import get_settings

logger = logging.getLogger("ecopath.gemini")
settings = get_settings()

# Configure Gemini SDK
genai.configure(api_key=settings.gemini_api_key)

# Safety settings: allow ecological/scientific content
_SAFETY = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

# ─── Model Instances ──────────────────────────────────────────────────────────


def _get_pro_model():
    return genai.GenerativeModel(
        model_name=settings.gemini_pro_model,
        safety_settings=_SAFETY,
        generation_config=genai.GenerationConfig(
            temperature=0.7,
            top_p=0.95,
            max_output_tokens=2048,
        ),
    )


def _get_flash_model():
    return genai.GenerativeModel(
        model_name=settings.gemini_flash_model,
        safety_settings=_SAFETY,
        generation_config=genai.GenerationConfig(
            temperature=0.2,  # Lower for more deterministic ID
            max_output_tokens=512,
        ),
    )


# ─── Vision ID (Flash) ────────────────────────────────────────────────────────
async def identify_bird_from_image(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
) -> dict[str, Any]:
    """
    Use Gemini Flash to identify a bird species from an image.
    Also detects if input is a drawing/screenshot/low-quality photo (spoof detection).

    Returns a structured dict with species identification and confidence.
    """
    model = _get_flash_model()

    prompt = """You are an expert ornithologist with comprehensive knowledge of bird species worldwide.

Analyze this image carefully and respond with a JSON object only (no markdown, no explanation):

{
  "is_bird": true/false,
  "is_real_photo": true/false,
  "spoof_warning": "description if not a real photo, else null",
  "identified": true/false,
  "common_name": "species common name or null",
  "scientific_name": "species scientific name or null",
  "confidence": 0.0-1.0,
  "native_range": ["list of regions/countries where this species naturally occurs"],
  "reasoning": "Brief explanation of identification features observed",
  "alternative_species": ["possible alt 1", "possible alt 2"] or []
}

Rules:
- is_real_photo = false if image is a drawing, screenshot, painting, or manipulated
- identified = false if you cannot confidently identify the species
- confidence must reflect your true certainty (0.95+ only for certain ID)
- native_range should list the actual geographic range of the species, not the observer's location
- If not a bird, set all identification fields to null"""

    image_part = {
        "mime_type": mime_type,
        "data": base64.b64encode(image_bytes).decode("utf-8"),
    }

    try:
        response = await model.generate_content_async([prompt, image_part])
        raw = response.text.strip()

        # Clean potential markdown code fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        result = json.loads(raw)
        return result
    except json.JSONDecodeError:
        logger.error(f"Gemini Flash returned non-JSON: {response.text[:200]}")
        return {
            "is_bird": False,
            "is_real_photo": False,
            "identified": False,
            "confidence": 0.0,
            "reasoning": "Failed to parse identification response.",
        }
    except Exception as e:
        logger.error(f"Gemini Flash vision error: {e}")
        raise


# ─── Causal Reasoning — Streaming ────────────────────────────────────────────
async def stream_causal_reasoning(
    messages: list[dict[str, str]],
    species_context: Optional[dict[str, Any]] = None,
    anomaly_context: Optional[dict[str, Any]] = None,
    weather_context: Optional[dict[str, Any]] = None,
) -> AsyncIterator[str]:
    """
    Stream a causal reasoning response from Gemini Pro.
    Implements a RAG-like pattern by injecting retrieved context as system_instruction.

    Geography-agnostic: works for any bird species worldwide, not just Indian species.
    """
    context_blocks = []

    if species_context:
        native_range = species_context.get(
            "native_range") or species_context.get("primary_range") or []
        habitat = species_context.get(
            "habitat") or species_context.get("primary_habitat") or []
        iucn = species_context.get("iucn_status", "Unknown")
        migratory = species_context.get("migratory", False)

        context_blocks.append(f"""## Species: {species_context.get('common_name')} ({species_context.get('scientific_name')})
- Family: {species_context.get('family', 'Unknown')}
- Order: {species_context.get('order', 'Unknown')}
- IUCN Status: {iucn}
- Native Range: {', '.join(native_range) if native_range else 'Unknown'}
- Primary Habitat: {', '.join(habitat) if habitat else 'Unknown'}
- Migratory: {migratory}""")

        # Only include endemism info if it's actually meaningful (i.e., the species IS endemic somewhere)
        endemic_region = species_context.get("endemic_region")
        if endemic_region:
            context_blocks[-1] += f"\n- Endemic to: {endemic_region}"

    if anomaly_context:
        context_blocks.append(f"""## Detected Population Anomaly
- Year: {anomaly_context.get('year')}
- Type: {anomaly_context.get('anomaly_type')} ({anomaly_context.get('severity')} severity)
- Magnitude: {anomaly_context.get('magnitude_pct', 0):.1f}% deviation from 5-year average
- Observed count: {anomaly_context.get('observed_count')}
- Expected count: {anomaly_context.get('expected_count')}
- Affected region: {anomaly_context.get('affected_region') or anomaly_context.get('affected_state', 'Unknown')}""")

    if weather_context:
        context_blocks.append(f"""## Environmental Context for Anomaly Year
- Annual precipitation: {weather_context.get('annual_precipitation_mm', 'N/A')} mm
- Seasonal precipitation: {weather_context.get('monsoon_precipitation_mm', 'N/A')} mm
- Extreme heat days (>40°C): {weather_context.get('extreme_heat_days_gt40c', 'N/A')}
- Dry days: {weather_context.get('dry_days_count', 'N/A')}
- Avg max temperature: {weather_context.get('annual_avg_temp_max', 'N/A')}°C""")

    rag_context = "\n\n".join(context_blocks)

    # Determine geographic focus from context for tailored but not restrictive guidance
    affected_region = (
        (anomaly_context or {}).get("affected_region")
        or (anomaly_context or {}).get("affected_state")
        or (
            ", ".join((species_context or {}).get("native_range")
                      or (species_context or {}).get("primary_range") or [])
        )
        or "the relevant region"
    )

    system_prompt = f"""You are EcoPath's Causal Reasoning Agent — an expert ecological intelligence system with deep knowledge of global bird biodiversity, population dynamics, and conservation science.

Your role is to:
1. Explain population anomalies (surges/dips) using rigorous causal reasoning grounded in the species' actual biology and native range
2. Connect environmental patterns (weather, habitat change, human activity) to population outcomes
3. Provide scientifically grounded hypotheses, clearly distinguishing known facts from inference
4. Reference real ecological events relevant to the species and region (e.g. droughts, cyclones, El Niño, conservation actions, land use change)
5. Be concise, precise, and use markdown for structure

Tailor your analysis to {affected_region} and the species' known ecology. Do not force a regional framing that doesn't fit the species — if the species is not native to a given region, address that honestly and pivot to what is ecologically relevant and useful.

Always tag evidence type:
- 📊 Statistical evidence (from population data)
- 🌦️ Weather/climate evidence
- 📚 Known ecological fact
- 🔬 Scientific hypothesis

{f"## Retrieved Context{chr(10)}{rag_context}" if rag_context else "No specific context was retrieved. Reason from general ecological principles and flag that species-specific data is unavailable."}"""

    model = genai.GenerativeModel(
        model_name=settings.gemini_pro_model,
        safety_settings=_SAFETY,
        generation_config=genai.GenerationConfig(
            temperature=0.7,
            top_p=0.95,
            max_output_tokens=2048,
        ),
        system_instruction=system_prompt,
    )

    # Build Gemini chat history
    chat_history = []
    for msg in messages[:-1]:
        chat_history.append({
            "role": "user" if msg["role"] == "user" else "model",
            "parts": [msg["content"]],
        })

    chat = model.start_chat(history=chat_history)
    last_message = messages[-1]["content"] if messages else "Hello"

    try:
        response = await chat.send_message_async(last_message, stream=True)
        async for chunk in response:
            if chunk.text:
                yield chunk.text
    except Exception as e:
        logger.error(f"Gemini streaming error: {e}")
        yield f"\n\n⚠️ Reasoning engine encountered an error: {str(e)}"


# ─── Generate Species Description ────────────────────────────────────────────
async def generate_species_description(
    common_name: str,
    scientific_name: str,
    iucn_status: str,
    habitat: list[str],
    native_range: Optional[list[str]] = None,
) -> str:
    """Generate a rich, 3-paragraph species description for the dashboard."""
    model = _get_pro_model()

    range_str = ", ".join(native_range) if native_range else "its native range"

    prompt = f"""Write a scientifically accurate, engaging 3-paragraph description of the {common_name} ({scientific_name}) 
for a global biodiversity dashboard aimed at ecologists and nature enthusiasts.

Include:
1. Physical characteristics and identification features
2. Ecological role, diet, and behaviour in {range_str}
3. Conservation status ({iucn_status}) and the primary threats and conservation efforts relevant to this species

Habitat: {', '.join(habitat) if habitat else 'Unknown'}
Style: Authoritative but accessible. No markdown, plain paragraphs only.
Do not assume a specific country as the audience — write for a global reader interested in this species."""

    try:
        response = await model.generate_content_async(prompt)
        return response.text.strip()
    except Exception as e:
        logger.error(f"Description generation failed for {common_name}: {e}")
        return f"The {common_name} ({scientific_name}) is a bird species found in {range_str}."

# ─── Generate Ecology Answers ────────────────────────────────────────────────


async def generate_ecology_answers(common_name: str, scientific_name: str) -> dict[str, str]:
    """Generate 10 structured ecological answers for a given species."""
    # Force JSON mode specifically for this endpoint
    model = genai.GenerativeModel(
        model_name=settings.gemini_pro_model,
        safety_settings=_SAFETY,
        generation_config=genai.GenerationConfig(
            temperature=0.7,
            top_p=0.95,
            max_output_tokens=2048,
            response_mime_type="application/json"
        )
    )

    prompt = f"""Provide factual, strictly ecological answers for the species {common_name} ({scientific_name}). Do not use conversational filler. Limit each answer to 4 concise sentences max.

Output the response strictly as a structured JSON object containing exactly these 10 keys:
- taxonomic_identity
- geographic_distribution
- diet
- predators
- activity_patterns
- reproductive_traits
- migration
- habitat
- threats
- population_trends
"""

    def _fallback_answers() -> dict[str, str]:
        species_label = f"{common_name} ({scientific_name})"
        return {
            "taxonomic_identity": f"{species_label} is a bird species documented in the EcoPath species dataset.",
            "geographic_distribution": f"{species_label} occurs within its documented native range, but the live Gemini service was unavailable during this request.",
            "diet": f"Dietary information for {species_label} could not be retrieved from Gemini, so this entry should be verified against authoritative field guides.",
            "predators": f"Predation pressure for {species_label} varies by habitat and life stage; the live ecological model did not return a detailed answer.",
            "activity_patterns": f"Activity patterns for {species_label} should be confirmed from a species account because Gemini did not return a live response.",
            "reproductive_traits": f"Reproductive traits for {species_label} were unavailable from the live service in this run.",
            "migration": f"Migration status for {species_label} should be verified from conservation references because Gemini was unavailable.",
            "habitat": f"{species_label} is associated with one or more habitat types in the species record, but no live Gemini explanation was available.",
            "threats": f"Potential threats to {species_label} may include habitat change and human disturbance, depending on range; verify with species-specific sources.",
            "population_trends": f"Population trend information for {species_label} was not returned by the live model and should be verified using conservation data.",
        }

    try:
        response = await model.generate_content_async(prompt)
        raw = response.text.strip()

        # Robustly strip markdown fences if present
        if raw.startswith("```"):
            lines = raw.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            raw = "\n".join(lines).strip()

        return json.loads(raw)
    except Exception as e:
        logger.error(
            f"Ecology data generation failed for {common_name}. Raw info: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return _fallback_answers()
