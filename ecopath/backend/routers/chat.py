import json
import logging
import asyncio
from fastapi import APIRouter, HTTPException, Request, Header
from fastapi.responses import StreamingResponse

from models.schemas import ChatRequest
from agent.agent_loop import run_agent_turn
from agent.session import delete_session, peek_session

logger = logging.getLogger("ecopath.chat")
router = APIRouter()


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/stream")
async def chat_stream(request: Request, body: ChatRequest, x_session_id: str = Header(default="default-session")):
    """
    Streaming SSE endpoint for the EcoPath Agent.
    """
    if not body.messages:
        raise HTTPException(status_code=400, detail="No messages provided")
    
    # We take the last user message to feed into the agent loop
    user_message = body.messages[-1].content

    async def event_generator():
        try:
            result = await run_agent_turn(user_message, x_session_id)

            # Tell the client its session had timed out before this turn ran, so it
            # can say so inline rather than silently losing the thread.
            if result.session_expired:
                yield _sse("session_expired", {"session_id": x_session_id})

            for block in result.blocks:
                block_type = block.get("type")
                
                if block_type == "narrative":
                    yield _sse("block_start", {"type": "narrative"})
                    content = block.get("content", "")
                    
                    # Split into chunks of 3-5 words
                    words = content.split(' ')
                    chunk_size = 4
                    for i in range(0, len(words), chunk_size):
                        chunk = " ".join(words[i:i+chunk_size])
                        if i + chunk_size < len(words):
                            chunk += " "
                        
                        yield _sse("text_delta", {"content": chunk})
                        await asyncio.sleep(0.04) # Simulate typing 40ms delay
                        
                    yield _sse("block_end", {"type": "narrative"})
                
                else:
                    yield _sse("block", block)

            # Current research focus, emitted once at the end of the response.
            yield _sse("session_state", result.session_state)

            # Send done signal
            yield _sse("done", {})

        except Exception as e:
            logger.error(f"Chat stream error: {e}")
            error_block = {
                "type": "narrative",
                "content": f"\n\n⚠️ An error occurred: {str(e)}"
            }
            yield _sse("block", error_block)
            yield _sse("done", {})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )

@router.post("/")
async def chat_non_streaming(body: ChatRequest, x_session_id: str = Header(default="default-session")):
    """
    Non-streaming fallback chat endpoint.
    """
    if not body.messages:
        raise HTTPException(status_code=400, detail="No messages provided")
        
    user_message = body.messages[-1].content
    return (await run_agent_turn(user_message, x_session_id)).blocks


@router.post("/reset")
async def reset_session(x_session_id: str = Header(default="default-session")):
    """Clear a research session. The client generates a fresh session id afterwards."""
    existed = delete_session(x_session_id)
    logger.info(f"Reset session {x_session_id} (existed={existed})")
    return {"status": "ok", "message": "Session reset", "existed": existed}


@router.get("/session/{session_id}")
async def get_session_debug(session_id: str):
    """Inspect a live session's state. Debug aid for verifying context tracking."""
    session = peek_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="No active session with that id")
    return session.to_debug_dict()
