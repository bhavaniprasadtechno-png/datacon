import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface MarkdownMessageProps {
  content: string;
  streaming?: boolean;
}

export function MarkdownMessage({ content, streaming }: MarkdownMessageProps) {
  if (!content) return null;

  return (
    <div
      style={{
        fontSize: 13.5,
        lineHeight: 1.6,
        color: "var(--ac-fg)",
        wordBreak: "break-word",
      }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p style={{ margin: "0 0 10px 0", lineHeight: 1.6 }}>{children}</p>,
          strong: ({ children }) => <strong style={{ fontWeight: 600, color: "var(--ac-fg)" }}>{children}</strong>,
          em: ({ children }) => <em style={{ fontStyle: "italic" }}>{children}</em>,
          ul: ({ children }) => (
            <ul style={{ margin: "6px 0 12px 0", paddingLeft: 20, listStyleType: "disc" }}>
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol style={{ margin: "6px 0 12px 0", paddingLeft: 20, listStyleType: "decimal" }}>
              {children}
            </ol>
          ),
          li: ({ children }) => (
            <li style={{ marginBottom: 6, lineHeight: 1.55 }}>
              {children}
            </li>
          ),
          h1: ({ children }) => (
            <h1 style={{ fontSize: 16, fontWeight: 700, margin: "14px 0 8px 0", color: "var(--ac-fg)" }}>
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 style={{ fontSize: 15, fontWeight: 700, margin: "12px 0 6px 0", color: "var(--ac-fg)" }}>
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 style={{ fontSize: 14, fontWeight: 700, margin: "10px 0 4px 0", color: "var(--ac-fg)" }}>
              {children}
            </h3>
          ),
          h4: ({ children }) => (
            <h4 style={{ fontSize: 13.5, fontWeight: 700, margin: "8px 0 4px 0", color: "var(--ac-fg)" }}>
              {children}
            </h4>
          ),
          code: ({ children, className }) => {
            const isBlock = className?.includes("language-");
            if (isBlock) {
              return (
                <pre
                  style={{
                    background: "var(--ac-bg-muted)",
                    padding: "10px 14px",
                    borderRadius: 8,
                    overflowX: "auto",
                    fontSize: 12,
                    margin: "10px 0",
                    border: "1px solid var(--ac-border)",
                  }}
                >
                  <code>{children}</code>
                </pre>
              );
            }
            return (
              <code
                style={{
                  background: "var(--ac-bg-muted)",
                  padding: "2px 6px",
                  borderRadius: 4,
                  fontSize: 12,
                  fontFamily: "'IBM Plex Mono', monospace",
                  border: "1px solid var(--ac-border)",
                  color: "var(--ac-deep, #4338ca)",
                }}
              >
                {children}
              </code>
            );
          },
          table: ({ children }) => (
            <div style={{ overflowX: "auto", margin: "10px 0", border: "1px solid var(--ac-border)", borderRadius: 8 }}>
              <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 12.5 }}>{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead style={{ background: "var(--ac-bg-muted)" }}>{children}</thead>,
          th: ({ children }) => (
            <th style={{ borderBottom: "1px solid var(--ac-border)", padding: "6px 10px", textAlign: "left", fontWeight: 600 }}>
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td style={{ borderBottom: "1px solid var(--ac-border)", padding: "6px 10px" }}>{children}</td>
          ),
          blockquote: ({ children }) => (
            <blockquote
              style={{
                borderLeft: "3px solid var(--ac)",
                paddingLeft: 10,
                margin: "8px 0",
                color: "var(--ac-muted)",
                fontStyle: "italic",
              }}
            >
              {children}
            </blockquote>
          ),
          hr: () => <hr style={{ border: "none", borderTop: "1px solid var(--ac-border)", margin: "14px 0" }} />,
        }}
      >
        {content}
      </ReactMarkdown>
      {streaming && (
        <span
          style={{
            display: "inline-block",
            width: 7,
            height: 14,
            background: "var(--ac)",
            marginLeft: 2,
            animation: "dvblink .9s infinite",
            verticalAlign: "middle",
          }}
        />
      )}
    </div>
  );
}
