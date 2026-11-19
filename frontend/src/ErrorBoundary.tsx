import { Component, type ErrorInfo, type ReactNode } from "react";

/** Shows what went wrong (instead of a blank white page) and offers a reload. */
export default class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("UI crashed:", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="mx-auto max-w-xl p-10 text-center">
        <div className="text-4xl">⚠️</div>
        <h1 className="mt-2 text-xl font-semibold text-slate-900">Something went wrong on this screen</h1>
        <p className="mt-2 break-words font-mono text-sm text-rose-700">{this.state.error.message}</p>
        <p className="mt-2 text-sm text-slate-500">Your trip is saved. Reloading usually fixes this.</p>
        <div className="mt-5 flex justify-center gap-2">
          <button onClick={() => location.reload()} className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white">Reload</button>
          <button onClick={() => { location.href = location.pathname; }} className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold">Back to all trips</button>
        </div>
      </div>
    );
  }
}
