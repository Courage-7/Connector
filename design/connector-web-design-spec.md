# Connector web design specification

Status: proposed for approval  
Scope: desktop web application and public landing page  
Product name: **Connector**

## Source of truth

Only these three visual artifacts are authoritative:

1. `connector-web-authoritative-hero.png`
2. `connector-web-authoritative-ecosystem.png`
3. `connector-web-interaction-storyboard.png`

All earlier concept renders are exploratory and must not be used to infer component styles, spacing, copy, or behavior.

## Design direction

Connector is a premium infrastructure product for governed access between tools and AI agents. The interface should feel precise, quiet, secure, and alive. It must not resemble a white generic SaaS template.

- Theme: locked deep midnight green
- Primary accent: emerald
- Provider colors: authentic brand colors inside provider icons only
- Visual density: medium-low, with strong negative space
- Shape language: one floating pill header, pill actions, restrained rounded icon containers, and subtle technical rails
- Decorative language: orbital paths, routing nodes, and switchboard lines
- Avoid: purple, excessive glow, fake metrics, testimonials, pricing blocks, repeated equal card grids, and visual noise

## Page architecture

- `/`: public landing page
- `/app/`: authenticated Connector workspace

Landing-page sequence:

1. Hero and kinetic connector constellation
2. Expanded connector ecosystem
3. Governed workflow: connect, scope, request, approve, audit
4. Security and untrusted-data explanation
5. Closing action and footer

The current Supabase workflow remains functional inside `/app/`. The dashboard product label becomes `Connector` everywhere.

## Header

- Centered floating island, not edge-to-edge
- Desktop maximum width: 980px
- Height: 74px at page top, 66px after scroll settlement
- Top offset: 40px
- Full pill radius
- Dark translucent surface with one thin emerald-tinted border
- Left: Connector gateway-C mark and wordmark
- Center/right links: `Integrations`, `Security`, `How it works`
- Final action: `Open workspace`

The header component is identical on every landing-page section. It is never redrawn with different radii, spacing, borders, or logo proportions.

## Hero

Headline:

> Connect your tools. Keep control.

Supporting copy:

> A secure control plane for data, email, calendars, and the agents that use them.

Actions:

- Primary: `Open workspace`
- Secondary: `Explore connectors`

The right side contains a kinetic constellation centered on the Connector mark. Provider icons use varied sizes and orbital depths. This is an ecosystem, not a uniform icon grid.

Hero providers shown: Supabase, Gmail, Outlook, Google Calendar, Slack, Microsoft Teams, GitHub, Notion, Google Drive, and AI agents.

## Connector ecosystem

Headline:

> Your tools, one governed path.

Supporting copy:

> Bring data, communication, files, and work systems into the same controlled agent workflow.

Closing line:

> One policy layer. More of your stack.

The ecosystem uses four labeled routing lanes that converge on the Connector mark:

| Lane | Providers |
| --- | --- |
| Data | Supabase, PostgreSQL, Snowflake |
| Communication | Gmail, Outlook, Slack, Microsoft Teams, Google Calendar |
| Knowledge & files | Notion, Google Drive, OneDrive, Dropbox |
| Work & developer | GitHub, Linear, Jira, HubSpot, Salesforce |

Availability is explicit and truthful:

| Status | Providers |
| --- | --- |
| Live now | Supabase |
| Next | Gmail, Outlook, Google Calendar, GitHub |
| Planned | PostgreSQL, Snowflake, Slack, Microsoft Teams, Notion, Google Drive, OneDrive, Dropbox, Linear, Jira, HubSpot, Salesforce |

AI agents are the governed consumer layer, not presented as a connector that is already authorized by default.

## Component rules

### Color tokens

| Token | Value | Use |
| --- | --- | --- |
| Canvas | `#021411` | Page background |
| Elevated canvas | `#06201B` | Header and major surfaces |
| Surface | `#0A2A23` | Icon containers and controls |
| Text | `#F3F4EF` | Headings and primary labels |
| Muted text | `#A6B5AE` | Supporting copy |
| Accent | `#18C980` | Brand mark, primary actions, live state |
| Accent bright | `#29DE94` | Hover and active route only |
| Border | `rgba(70, 205, 151, 0.30)` | Standard outlines |
| Muted state | `#77837E` | Planned state |

### Typography

- Primary family: Geist Sans or a metrically compatible self-hosted fallback
- Metadata family: Geist Mono where useful, never for long prose
- Hero: 72–84px, weight 620–680, line height 0.98, tight tracking
- Section heading: 56–68px, weight 620–680
- Body: 18–22px, line height 1.45–1.55
- Navigation and actions: 16px, weight 500–600
- No all-caps marketing labels above headings

### Geometry

- Header and large actions: full pill radius
- Provider icon containers: 16px radius
- Major application surfaces: 18px radius
- Small controls: 10–12px radius
- Standard border: 1px
- Primary action height: 56px
- Icon-container sizes vary by hierarchy; they must not become a uniform grid

### Consistency contract

- One logo asset and one wordmark lockup
- One header component
- One primary button component
- One secondary button component
- One provider-icon container component with size variants only
- One availability-dot component with `live`, `next`, and `planned` variants
- One routing-line system
- No section-specific reinterpretation of these components

## Interaction and motion

Motion communicates routing and connection state. It must remain subtle enough for a security product.

| Interaction | Behavior | Timing |
| --- | --- | --- |
| Initial header | Settles from 12px above with opacity | 420ms |
| Scrolled header | Moves up 8px, height reduces to 66px, surface becomes slightly more opaque | 220ms |
| Primary button hover | Surface brightens; arrow translates 4px right | 180ms |
| Secondary button hover | Border and text brighten; faint internal tint appears | 180ms |
| Navigation hover | Underline grows from the link center | 160ms |
| Provider hover | Container rises 6px and scales to 1.02; route brightens; truthful status label appears | 180ms |
| Provider focus | Same information as hover plus a 2px visible focus ring | Immediate / 160ms color transition |
| Hero orbit | Icons advance slowly on separate elliptical paths while staying upright | 18–32s per orbit |
| Route pulse | Nodes illuminate in sequence toward the Connector mark | 700ms |
| Ecosystem lane hover | Selected lane and route brighten; unrelated lanes reduce to 45% opacity | 200ms |
| Section entrance | Heading and content rise 24px with a short stagger | 420–560ms |
| Workflow progression | Connection line draws once as stages enter the viewport | 700ms |
| Closing convergence | Provider nodes move slightly toward the Connector mark once | 900ms |

Implementation constraints:

- Animate transforms and opacity only where possible
- Do not animate layout dimensions continuously
- Use one continuous ambient animation region on the page: the hero constellation
- Other animations are user-triggered or one-shot scroll reveals
- Pause orbit motion when the document is hidden
- `prefers-reduced-motion: reduce` disables orbiting, pulses, drawn paths, and entrance movement; content remains fully visible and hover/focus still changes color and border contrast

## Accessibility

- Minimum 4.5:1 contrast for body copy and interactive labels
- Every hover disclosure has an equivalent keyboard-focus state
- Focus ring: 2px accent, 3px offset
- Provider icons include accessible names and visible status text on focus
- Planned integrations are not styled as enabled actions
- All landing-page navigation works without motion

## Approval boundary

No application code should be changed until this desktop web direction is approved. Mobile-specific design is deferred. After approval, implementation must match these three artifacts and this specification, followed by browser visual QA and live end-to-end Supabase acceptance tests.
