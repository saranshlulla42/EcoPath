import { ChatMessage } from '../../types/chat';
import { UserMessage } from './UserMessage';
import { AssistantMessage } from './AssistantMessage';
import { useAutoScroll } from '../../hooks/useAutoScroll';

export function ChatMessageList({
  messages,
  onFollowUp
}: {
  messages: ChatMessage[];
  onFollowUp?: (text: string) => void;
}) {
  // auto-scroll runs when messages array or deep block content changes
  const scrollRef = useAutoScroll<HTMLDivElement>([messages]);

  return (
    <div
      ref={scrollRef}
      style={{
        flex: 1,
        overflowY: "auto",
        padding: "2.5rem 1.5rem",
        width: "100%",
        boxSizing: "border-box",
      }}
    >
      <div style={{ maxWidth: 720, margin: '0 auto' }}>
        {messages.map((msg, i) => (
          msg.role === "user" ? (
            <UserMessage key={msg.id || i} message={msg} />
          ) : (
            <AssistantMessage key={msg.id || i} message={msg} onFollowUp={onFollowUp} />
          )
        ))}
      </div>
    </div>
  );
}
