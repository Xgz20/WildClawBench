# Timeline accessibility brief

Build a compact product-history timeline for readers using keyboards, screen readers, reduced-motion settings, and narrow mobile screens.

Requirements:

- Use a clear page heading and a short introduction.
- Render all records from `events.yaml` in chronological order.
- Each event must be a separate focusable control. Its details are collapsed initially.
- Tab must reach every event in order. Enter and Space must toggle the matching details without activating another event.
- Expose expanded/collapsed state and the controlled details region with appropriate semantic attributes.
- Provide a visible keyboard focus indicator.
- Do not rely on color alone to convey state.
- Disable nonessential animation under `prefers-reduced-motion: reduce`.
- At widths of 420px or less, content must fit without horizontal scrolling.
- The result must be one offline HTML file with inline CSS and JavaScript only. No external URLs, requests, fonts, images, or additional output files.
