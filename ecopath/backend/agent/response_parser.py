import json
import logging

logger = logging.getLogger("ecopath.agent.response_parser")

def parse_agent_response(raw_response: str) -> list[dict]:
    """
    Parses the raw JSON string from Gemini into a list of blocks.
    If Gemini failed to output valid JSON, falls back to wrapping
    the raw string in a single narrative block.
    """
    cleaned_str = raw_response.strip()
    
    # Strip markdown block formatting if Gemini ignored the instruction
    if cleaned_str.startswith("```json"):
        cleaned_str = cleaned_str[7:]
    if cleaned_str.startswith("```"):
        cleaned_str = cleaned_str[3:]
    if cleaned_str.endswith("```"):
        cleaned_str = cleaned_str[:-3]
    cleaned_str = cleaned_str.strip()
    
    try:
        data = json.loads(cleaned_str)
        blocks = data.get("blocks", [])
        if not isinstance(blocks, list):
            raise ValueError("Parsed JSON does not contain a 'blocks' list.")
        return blocks
    except Exception as e:
        logger.warning(f"Failed to parse agent response as JSON: {e}. Falling back to raw text.")
        return [
            {
                "type": "narrative",
                "content": raw_response
            },
            {
                "type": "follow_ups",
                "suggestions": ["Can you try asking that again in a different way?"]
            }
        ]
