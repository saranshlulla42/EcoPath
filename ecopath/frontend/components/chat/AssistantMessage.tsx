import { ChatMessage } from '../../types/chat';
import { BlockRenderer } from './BlockRenderer';
import { AnimatedBlockWrapper } from './AnimatedBlockWrapper';
import { ThinkingIndicator } from './ThinkingIndicator';

export function AssistantMessage({ 
  message,
  onFollowUp 
}: { 
  message: ChatMessage;
  onFollowUp?: (text: string) => void;
}) {
  return (
    <div style={{ 
      display: "flex", 
      gap: "16px", 
      marginBottom: "28px", 
      alignItems: "flex-start",
      width: "100%",
      maxWidth: "720px",
      margin: "0 auto 28px auto",
    }}>
      <div style={{
        width: 2,
        background: "var(--accent-primary)",
        borderRadius: 1,
        flexShrink: 0,
        marginTop: 4,
        alignSelf: "stretch",
        minHeight: 20,
        opacity: 0.6
      }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        {message.notice && (
          <p style={{
            fontFamily: "var(--font-mono, monospace)",
            fontSize: "0.68rem",
            letterSpacing: "0.06em",
            color: "var(--text-tertiary)",
            marginBottom: "0.75rem",
          }}>
            {message.notice}
          </p>
        )}
        {message.blocks.map((block, index) => (
          <AnimatedBlockWrapper key={index} index={index}>
            <BlockRenderer
              block={block}
              isLastBlock={index === message.blocks.length - 1}
              onFollowUp={onFollowUp}
            />
          </AnimatedBlockWrapper>
        ))}
        {message.blocks.length === 0 && message.isStreaming && (
          <ThinkingIndicator />
        )}
      </div>
    </div>
  );
}
