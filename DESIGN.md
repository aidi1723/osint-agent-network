# OSINT Agent Network UI Design Brief

## Product Feel

The interface is a dense technical operations console for long-running intelligence work. It should feel calm, precise, and trustworthy: more like a security analyst workstation than a marketing SaaS landing page.

## Visual Principles

- First screen is the working dashboard, not a hero page.
- Prioritize scanning, filtering, comparison, and repeated operator action.
- Use compact surfaces, clear status colors, and strong hierarchy.
- Avoid decorative gradients, large promotional cards, and oversized headings.
- Keep typography crisp and utilitarian.

## Color Roles

- Background: light neutral gray, close to white but easier on long viewing.
- Surface: white and very pale blue-gray panels.
- Text: black or near-black neutral.
- Muted text: medium slate gray.
- Border: subtle cool gray line.
- Accent: cyan or blue for primary actions and selected states.
- Success: green.
- Warning: amber.
- Danger: red.
- Unknown/weak confidence: gray.

## Typography

- Use a modern sans font for UI labels and body.
- Use a monospace font for targets, domains, IPs, IDs, commands, and evidence snippets.
- Headings should be compact and proportional to admin panels.
- No viewport-scaled font sizes.
- Letter spacing stays at `0`.

## Layout

- Desktop-first, responsive down to tablet/mobile.
- Use a persistent left navigation rail on desktop.
- Main content uses dense tables, split panes, tabs, and detail drawers.
- Cards are only for repeated summary blocks, not page-section decoration.
- Radius should stay at 8px or less.

## Components

- Buttons use icons where familiar actions exist.
- Tool toggles use switches or checkboxes.
- Strategy selection uses segmented controls.
- Confidence filtering uses tabs, chips, or compact select controls.
- Investigation and entity lists use tables with sticky headers where useful.
- Long-running jobs show progress, heartbeat, logs, and cancel controls.

## Required States

- Empty dashboard.
- Tool disabled.
- Tool missing executable.
- Credential blocked.
- Running and streaming.
- Partial failure.
- No findings.
- Contradicted evidence.
- Cancelled job.

## Motion

Motion should be restrained and functional:

- Short hover/focus transitions.
- Subtle row highlight.
- Smooth drawer open/close.
- No dramatic decorative animation.

## Accessibility

- Preserve keyboard focus states.
- Ensure status colors also include labels or icons.
- Maintain readable contrast in light mode.
- Tables and forms must remain usable on narrow screens.
