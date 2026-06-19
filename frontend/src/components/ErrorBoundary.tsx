import { Component, type ErrorInfo, type ReactNode } from "react";

/** Catches render errors so a bug shows a recoverable message instead of a blank screen. */
export default class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("UI render error:", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="h-full flex flex-col items-center justify-center gap-4 p-8 text-center bg-paper text-ink">
          <div className="font-serif text-2xl font-semibold">Something went wrong</div>
          <p className="text-sm text-muted max-w-md break-words">{this.state.error.message}</p>
          <button
            onClick={() => location.reload()}
            className="px-4 h-9 rounded-field bg-signal-grad text-white text-sm font-semibold"
          >
            Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
