import { useState, useRef, useCallback } from 'react';
import { ChatMessage, Block, NarrativeBlock, SessionState } from '../types/chat';

export interface ChatEndpoints {
  /** SSE endpoint that streams an agent turn. */
  streamUrl: string;
  /** Endpoint that clears the server-side research session. Optional (mock mode). */
  resetUrl?: string;
}

const EXPIRY_NOTICE = 'Session expired. Starting a fresh conversation.';

export function useSSEChat(endpoints: ChatEndpoints | string) {
  const { streamUrl, resetUrl } =
    typeof endpoints === 'string' ? { streamUrl: endpoints, resetUrl: undefined } : endpoints;

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [sessionState, setSessionState] = useState<SessionState | null>(null);
  // Bumped on every follow-up chip click so the context bar can flash.
  const [contextPulse, setContextPulse] = useState(0);
  const sessionIdRef = useRef(crypto.randomUUID());

  const resetConversation = useCallback(async () => {
    const previousSessionId = sessionIdRef.current;

    // Rotate locally first, so a slow or failed reset can't leave the next
    // message attached to the session we're abandoning.
    sessionIdRef.current = crypto.randomUUID();
    setMessages([]);
    setSessionState(null);
    setContextPulse(0);
    setIsConnected(false);

    if (!resetUrl) return;
    try {
      await fetch(resetUrl, {
        method: 'POST',
        headers: { 'X-Session-ID': previousSessionId },
      });
    } catch (error) {
      // The server session will lapse on its own TTL, and we've already moved to
      // a new id, so a failed reset is not worth interrupting the user for.
      console.warn('Session reset request failed:', error);
    }
  }, [resetUrl]);

  const sendMessage = useCallback(async (text: string, options?: { fromFollowUp?: boolean }) => {
    if (!text.trim()) return;

    if (options?.fromFollowUp) {
      // Confirm to the user that the pending reference resolves against the
      // context they can see.
      setContextPulse((n) => n + 1);
    }

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      blocks: [{ type: 'narrative', content: text, isStreaming: false }],
      isStreaming: false,
    };

    const assistantId = crypto.randomUUID();
    const initialAssistantMessage: ChatMessage = {
      id: assistantId,
      role: 'assistant',
      blocks: [],
      isStreaming: true,
    };

    setMessages((prev) => [...prev, userMessage, initialAssistantMessage]);
    setIsConnected(true);

    try {
      const response = await fetch(streamUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Session-ID': sessionIdRef.current,
        },
        body: JSON.stringify({
          messages: [...messages, userMessage].map((m) => ({
            role: m.role,
            content: m.blocks.map(b => (b as NarrativeBlock).content).join('\n'), // simplistic serialization for backend compat
          })),
        }),
      });

      if (!response.body) throw new Error('No response body');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      let isStreamActive = true;
      let streamTimeout = setTimeout(() => {
        isStreamActive = false;
        reader.cancel();
      }, 30000); // 30 second timeout on first chunk

      const processEvent = (eventStr: string) => {
        const lines = eventStr.split('\n');
        let eventType = 'message';
        let data = '';

        for (const line of lines) {
          if (line.startsWith('event:')) {
            eventType = line.substring(6).trim();
          } else if (line.startsWith('data:')) {
            data = line.substring(5).trim();
          }
        }

        if (!data) return;

        let parsedData: any;
        try {
          parsedData = JSON.parse(data);
        } catch (e) {
          // ignore parse errors for partial/malformed data, but log
          console.warn('Failed to parse SSE data:', data);
          return;
        }

        // The research focus lives outside the message list — the backend sends
        // it once, at the end of the turn.
        if (eventType === 'session_state') {
          setSessionState(parsedData as SessionState);
          return;
        }

        setMessages((prev) => {
          const currentMsgs = [...prev];
          const lastMsgIndex = currentMsgs.length - 1;
          const msg = { ...currentMsgs[lastMsgIndex] };
          let updatedBlocks = [...msg.blocks];

          if (eventType === 'session_expired') {
            // The backend already opened a fresh session under this id and
            // answered from it, so the id stays put — only the stale local
            // context needs clearing. Earlier messages remain on screen.
            msg.notice = EXPIRY_NOTICE;
            setSessionState(null);
          } else if (eventType === 'block_start' && parsedData.type === 'narrative') {
            updatedBlocks.push({ type: 'narrative', content: '', isStreaming: true });
          } else if (eventType === 'text_delta') {
            const lastBlock = { ...updatedBlocks[updatedBlocks.length - 1] } as NarrativeBlock;
            if (lastBlock && lastBlock.type === 'narrative') {
              lastBlock.content += parsedData.content || '';
              updatedBlocks[updatedBlocks.length - 1] = lastBlock;
            }
          } else if (eventType === 'block_end') {
            const lastBlock = { ...updatedBlocks[updatedBlocks.length - 1] } as NarrativeBlock;
            if (lastBlock && lastBlock.type === 'narrative') {
              lastBlock.isStreaming = false;
              updatedBlocks[updatedBlocks.length - 1] = lastBlock;
            }
          } else if (eventType === 'block') {
            updatedBlocks.push(parsedData);
          } else if (eventType === 'done') {
            msg.isStreaming = false;
          }

          msg.blocks = updatedBlocks;
          currentMsgs[lastMsgIndex] = msg;
          return currentMsgs;
        });
      };

      while (isStreamActive) {
        const { done, value } = await reader.read();
        if (done) break;

        clearTimeout(streamTimeout);
        streamTimeout = setTimeout(() => {
          isStreamActive = false;
          reader.cancel();
        }, 15000); // 15 seconds between chunks

        buffer += decoder.decode(value, { stream: true });
        
        let boundaryIndex;
        while ((boundaryIndex = buffer.indexOf('\n\n')) !== -1) {
          const eventStr = buffer.slice(0, boundaryIndex);
          buffer = buffer.slice(boundaryIndex + 2);
          processEvent(eventStr);
        }
      }
      clearTimeout(streamTimeout);

    } catch (error) {
      console.error('SSE Error:', error);
      setMessages((prev) => {
        const currentMsgs = [...prev];
        const lastMsgIndex = currentMsgs.length - 1;
        const msg = { ...currentMsgs[lastMsgIndex] };
        msg.isStreaming = false;
        
        // Ensure streaming states are closed
        msg.blocks = msg.blocks.map(b => b.type === 'narrative' ? { ...b, isStreaming: false } : b);
        
        msg.blocks.push({
          type: 'narrative',
          content: '\n\n⚠️ Response interrupted. Try again.',
          isStreaming: false
        });
        currentMsgs[lastMsgIndex] = msg;
        return currentMsgs;
      });
    } finally {
      setIsConnected(false);
      setMessages((prev) => {
        const currentMsgs = [...prev];
        const lastMsgIndex = currentMsgs.length - 1;
        if (currentMsgs[lastMsgIndex]?.isStreaming) {
           const msg = { ...currentMsgs[lastMsgIndex] };
           msg.isStreaming = false;
           msg.blocks = msg.blocks.map(b => b.type === 'narrative' ? { ...b, isStreaming: false } : b);
           currentMsgs[lastMsgIndex] = msg;
        }
        return currentMsgs;
      });
    }
  }, [streamUrl, messages]);

  return { messages, isConnected, sessionState, contextPulse, sendMessage, resetConversation };
}
