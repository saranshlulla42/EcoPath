import { ChatMessage, NarrativeBlock } from '../../types/chat';

export function UserMessage({ message }: { message: ChatMessage }) {
  // User messages only ever have a single narrative block in our data model
  const content = (message.blocks[0] as NarrativeBlock)?.content || '';

  return (
    <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "28px" }}>
      <div style={{
        maxWidth: "62%",
        padding: "0.75rem 1rem",
        background: "var(--accent-muted)",
        border: "1px solid var(--border)",
        borderRadius: "16px",
        fontFamily: "var(--font-sans, 'DM Sans')",
        fontSize: "0.9rem",
        lineHeight: 1.6,
        color: "var(--text-primary)",
      }}>
        {content}
      </div>
    </div>
  );
}
