# ARIA — Forest & Paper

Desktop design proposal and frontend implementation assets. Open
[presentation.html](presentation.html) in a browser; no server, package install,
fonts or network access is required. Use the arrow keys or Previous/Next. Print
uses twelve landscape pages. [ARIA-desktop-design.pdf](ARIA-desktop-design.pdf)
is the exported presentation for sharing.

- [Implementation brief](../../../docs/FRONTEND_DESIGN.md): screen behaviour,
  contract mappings, safety, layout and acceptance.
- [Frontend handoff](../../../docs/FRONTEND_HANDOFF.md): actual mock setup and types.
- [Frontend tasks](../../../agents/frontend.md): ordered implementation checklist.
- [design-tokens.json](design-tokens.json): proposed colours, type and dimensions.
- [tokens.css](tokens.css): matching CSS colour and core primitive variables.
- [assets/](assets/): SVG logo variants; full lockup, symbol, small symbol and icon.

The screen controls inside the presentation are **illustrations**, not working
agent actions. Only presentation navigation and printing are interactive. All
profile/message examples are fictional. The policy passage comes from a fictional
fixture. The NITDA reference informs colour only; official marks are not embedded
in the product design. Full dark mode is not specified; light content and a forest
sidebar are the recommended default. Accessibility themes remain required.

The HTML is editable source; the PDF is its snapshot. Re-export the PDF after
changing the HTML (Print → Save as PDF, background graphics enabled, CSS page size).
The developer should implement responsive React components rather than paste the
presentation markup into the app. Production text/targets follow the implementation
brief, not the scaled labels in the slides.
