# Connector dashboard design specification

Source of truth: `design/connector-dashboard-concept.png` (1536 × 1024).

## Product surface

- A real authenticated data browser, not a marketing page.
- Primary navigation: Connections, Data browser, Agent access, Audit.
- Active Supabase connection: 4TH-IR - SquadZero.
- Data browser: searchable relation rail, selected relation schema, live columns, and bounded row preview.
- Agent inspector: read-only state, approval requirement, row limit, selected columns, and approved execution.
- Empty/new-user path: Connect Supabase.

## Design tokens

- Background: `#ffffff`.
- Primary text: `#0b1730`.
- Muted text: `#607086`.
- Border: `#d9e0e9`.
- Quiet surface: `#f7f9fb`.
- Selected surface: `#eaf8f3`.
- Accent: `#00a86b`.
- Accent hover: `#008f5b`.
- Danger: `#b42318`.
- Radius: 6px controls, 8px contained inspector, 10px mobile connection summary.
- Shadow: none on desktop rails; one restrained `0 8px 24px rgb(11 23 48 / 8%)` shadow for modal or mobile overlays only.
- Type: system sans stack, 13px UI base, 12px labels, 20px selected-table heading, 600–700 weight for hierarchy.

## Desktop layout

- 52px top bar.
- 228px primary navigation rail.
- 220px searchable table rail.
- Flexible main workspace with horizontal overflow reserved for data tables.
- 256px agent inspector.
- Rails are separated by one-pixel borders and use open lists rather than card stacks.

## Responsive layout

- Below 1120px, the agent inspector becomes an inline section below the relation metadata.
- Below 820px, the primary rail becomes a four-item bottom navigation.
- The connection summary moves to the top of the content.
- The relation rail becomes a searchable list before a selected-table detail view.
- Preview tables scroll horizontally; columns never collapse into illegible cards.

## Component inventory

- App shell, top bar, primary navigation, connection summary.
- Table search, relation list row, selected relation header.
- Column definition table and row preview table.
- Agent access inspector, selected-column checkbox row, row-limit field, primary button.
- Loading, empty, error, pending-approval, and successful-query states.
- Connect Supabase button and OAuth return state.

## Interaction rules

- Selecting a relation loads its column definition before a preview can run.
- Independent connection and table requests run in parallel where possible.
- A preview always uses explicit columns and an enforced maximum row limit.
- Browser code never receives OAuth tokens, the connector admin token, or a stored tenant API key.
- Agent queries are read-only and auditable; the UI makes approval state visible before execution.

