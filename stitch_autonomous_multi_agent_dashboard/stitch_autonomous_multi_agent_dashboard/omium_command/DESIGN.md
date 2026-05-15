---
name: Omium Command
colors:
  surface: '#0b1326'
  surface-dim: '#0b1326'
  surface-bright: '#31394d'
  surface-container-lowest: '#060e20'
  surface-container-low: '#131b2e'
  surface-container: '#171f33'
  surface-container-high: '#222a3d'
  surface-container-highest: '#2d3449'
  on-surface: '#dae2fd'
  on-surface-variant: '#bac9cc'
  inverse-surface: '#dae2fd'
  inverse-on-surface: '#283044'
  outline: '#849396'
  outline-variant: '#3b494c'
  surface-tint: '#00daf3'
  primary: '#c3f5ff'
  on-primary: '#00363d'
  primary-container: '#00e5ff'
  on-primary-container: '#00626e'
  inverse-primary: '#006875'
  secondary: '#b7c8e1'
  on-secondary: '#213145'
  secondary-container: '#3a4a5f'
  on-secondary-container: '#a9bad3'
  tertiary: '#a8ffd2'
  on-tertiary: '#003824'
  tertiary-container: '#5be9ad'
  on-tertiary-container: '#006645'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#9cf0ff'
  primary-fixed-dim: '#00daf3'
  on-primary-fixed: '#001f24'
  on-primary-fixed-variant: '#004f58'
  secondary-fixed: '#d3e4fe'
  secondary-fixed-dim: '#b7c8e1'
  on-secondary-fixed: '#0b1c30'
  on-secondary-fixed-variant: '#38485d'
  tertiary-fixed: '#6ffbbe'
  tertiary-fixed-dim: '#4edea3'
  on-tertiary-fixed: '#002113'
  on-tertiary-fixed-variant: '#005236'
  background: '#0b1326'
  on-background: '#dae2fd'
  surface-variant: '#2d3449'
typography:
  display:
    fontFamily: Geist
    fontSize: 48px
    fontWeight: '700'
    lineHeight: '1.1'
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Geist
    fontSize: 32px
    fontWeight: '600'
    lineHeight: '1.2'
    letterSpacing: -0.01em
  headline-lg-mobile:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '600'
    lineHeight: '1.2'
  headline-md:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '600'
    lineHeight: '1.3'
  headline-sm:
    fontFamily: Geist
    fontSize: 20px
    fontWeight: '500'
    lineHeight: '1.4'
  body-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '400'
    lineHeight: '1.6'
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.6'
  body-sm:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: '1.5'
  label-caps:
    fontFamily: Geist
    fontSize: 12px
    fontWeight: '700'
    lineHeight: '1'
    letterSpacing: 0.05em
  code-sm:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '400'
    lineHeight: '1.4'
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  base: 4px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 40px
  gutter: 20px
  margin-mobile: 16px
  margin-desktop: 32px
---

## Brand & Style
The design system is engineered for high-stakes autonomous systems, prioritizing precision, technical authority, and calm under pressure. It evokes the feeling of a mission control center—sophisticated, dense with information, yet incredibly legible.

The aesthetic follows an **Enterprise Dark Mode** philosophy, blending **Corporate Modern** structures with **Subtle Glassmorphism**. This creates a sense of depth and hierarchy without distracting from critical data. Every element is designed to feel like a high-fidelity instrument: crisp, responsive, and trustworthy. The interface balances high-density information with intentional negative space to prevent cognitive overload during complex pipeline monitoring.

## Colors
The palette is rooted in deep, cinematic darkness to reduce eye strain during prolonged technical sessions.

- **Primary (Omium Blue):** An electric cyan used exclusively for primary actions, active states, and critical progress indicators. It should appear to "glow" against the dark background.
- **Surface Palette:** Utilizing a scale of Deep Slates and Charcoals. The background sits at `#020617`, with containers escalating through `#0F172A` and `#1E293B`.
- **Status Tones:** Success is represented by a cool Emerald, Warnings by a muted Amber, and Critical Errors by a high-chroma Crimson.
- **Accents:** Use semi-transparent white overlays (5-10% opacity) to create glassmorphic surfaces rather than solid grays.

## Typography
The typographic system prioritizes functional hierarchy. **Geist** provides a technical, slightly geometric edge for headings and navigation, while **Inter** ensures maximum readability for dense logs and data tables.

For specialized data—such as agent IDs, timestamps, and terminal outputs—**JetBrains Mono** is employed to provide a clear distinction between narrative UI text and system-generated data. Tight letter spacing is used on larger display styles to maintain a "machined" look, while body text retains standard tracking for legibility.

## Layout & Spacing
This design system utilizes a **Strict 12-Column Grid** for desktop views, optimized for dashboard "widgets" or "cards."

- **Desktop (1440px+):** 12 columns, 20px gutters, 32px side margins.
- **Tablet (768px - 1439px):** 8 columns, 16px gutters, 24px side margins.
- **Mobile (<768px):** 4 columns, 12px gutters, 16px side margins.

Spacing follows a 4px baseline rhythm. Information density is high, meaning internal card padding is often reduced to `md` (16px) to maximize the "at-a-glance" utility of the dashboard. Sections are separated by `xl` (40px) to provide visual breathing room between distinct logical modules.

## Elevation & Depth
Elevation in this system is conveyed through **Tonal Layers** and **1px Borders** rather than traditional heavy shadows.

1.  **Floor:** The base background is the lowest level (`#020617`).
2.  **Raised:** Cards and navigation panels use a subtle glass effect (Background Blur 12px, 40% Opacity) with a `1px` solid border (`#FFFFFF1A`).
3.  **Overlay:** Modals and tooltips use a higher background blur (24px) and a slightly brighter border (`#FFFFFF33`) to appear physically closer to the user.

Shadows, when used, are "Ambient Shadows"—ultra-diffused, low-opacity black (`#00000066`) with no offset, serving only to separate overlapping glass layers.

## Shapes
The shape language is **Technical and Soft-Rectangular**. A consistent `4px` (Soft) radius is applied to most UI components including buttons, cards, and input fields. This small radius maintains a precise, engineered feel while avoiding the harshness of 0px corners.

- **Standard Elements:** 4px (0.25rem).
- **Large Containers:** 8px (0.5rem).
- **Interactive Tags:** 2px or fully square for a terminal aesthetic.
- **Data Visualization Bars:** Square ends to emphasize accuracy and metrics.

## Components
- **Buttons:** Primary buttons are solid Omium Blue with black text for maximum contrast. Secondary buttons are ghost-style with a 1px border and white text.
- **Cards:** Defined by a semi-transparent background and a 1px border. Card headers should have a subtle bottom border (`1px`) to separate titles from content.
- **Status Indicators:** Small circular pips. For "Active" agents, use Omium Blue with a subtle 2px outer pulse animation.
- **Input Fields:** Darker than the card surface (`#020617`), with 1px slate borders. Focus state triggers an Omium Blue border and a subtle inner glow.
- **Data Tables:** Zebra striping is avoided; instead, use 1px horizontal dividers. Text should be primarily `body-sm` for high density.
- **Pipeline Nodes:** Represented by glassmorphic modules connected by 2px thick Omium Blue lines, indicating the flow of autonomous logic.