import { Component, type ReactNode, type ErrorInfo } from "react";
import { AlertCircle, RefreshCw } from "lucide-react";

interface Props {
  children: ReactNode;
  fallbackTitle?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Uncaught UI Error:", error, errorInfo);
  }

  private handleReload = () => {
    window.location.reload();
  };

  private handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  public render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            minHeight: "60vh",
            padding: 32,
            textAlign: "center",
            fontFamily: "system-ui, -apple-system, sans-serif",
          }}
        >
          <div
            style={{
              width: 56,
              height: 56,
              borderRadius: "50%",
              background: "#fdeee9",
              color: "#e2603f",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              marginBottom: 16,
            }}
          >
            <AlertCircle size={28} />
          </div>
          <h2 style={{ fontSize: 20, fontWeight: 700, margin: "0 0 8px", color: "var(--ac-fg, #1e293b)" }}>
            {this.props.fallbackTitle || "Something went wrong rendering this view"}
          </h2>
          <p style={{ fontSize: 13, color: "var(--ac-muted, #64748b)", maxWidth: 480, margin: "0 0 20px", lineHeight: 1.5 }}>
            {this.state.error?.message || "An unexpected error occurred in the user interface."}
          </p>
          <div style={{ display: "flex", gap: 12 }}>
            <button
              onClick={this.handleReset}
              style={{
                padding: "8px 16px",
                borderRadius: "var(--radius-sm, 6px)",
                background: "#fff",
                border: "1px solid var(--ac-border, #cbd5e1)",
                fontSize: 13,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Try Again
            </button>
            <button
              onClick={this.handleReload}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                padding: "8px 16px",
                borderRadius: "var(--radius-sm, 6px)",
                background: "var(--ac, #3b82f6)",
                color: "#fff",
                border: "none",
                fontSize: 13,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              <RefreshCw size={14} /> Reload Page
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
