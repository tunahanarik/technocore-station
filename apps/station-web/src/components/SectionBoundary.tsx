import { Component, type ReactNode } from "react";

/** Render failures stay inside the selected section; raw exception data is never shown. */
export class SectionBoundary extends Component<
  { readonly children: ReactNode }, { readonly failed: boolean }
> {
  override state = { failed: false };

  static getDerivedStateFromError() { return { failed: true }; }

  override render() {
    if (!this.state.failed) return this.props.children;
    return <section role="alert" className="rounded-lg border border-border p-4">
      <p>Bu bolum gosterilemedi. Baska bir bolume gecebilir veya yeniden deneyebilirsiniz.</p>
      <p className="font-mono text-xs">render_failed</p>
      <button type="button" onClick={() => this.setState({ failed: false })}>Bolumu yeniden dene</button>
    </section>;
  }
}
