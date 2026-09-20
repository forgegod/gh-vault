---
name: capability-wireframes
description: Use when a material feature changes a primary human-facing surface and needs a static CAP-linked wireframe.
version: 1.2.0
author: AI Software Blueprint
license: MIT
metadata:
  hermes:
    tags: [product, wireframes, ux, capability, documentation]
    related_skills: [application-records]
---

# Capability Wireframes

## Overview

Use a static, CAP-linked wireframe for every material capability that creates or
changes a primary human-facing surface. The wireframe makes the intended
interaction reviewable and remains a visual reference for the implemented
capability.

A CHG may own a review package at `docs/changes/reviews/CHG-<number>/`. It stays
review-only, including after closure. The implementation slice creates or updates
the separate canonical CAP wireframe with runtime behavior and executable evidence.
Never use the product inventory to make a proposal look like current behavior.

The portable layout is:

```text
docs/product/wireframes/
├── generate.mjs                    # canonical repository-owned generator
├── manifest.json                   # generated machine-readable inventory
├── index.html                      # generated human entry point
├── html/CAP-NNNN-<slug>.html       # generated per-CAP review source
└── exports/CAP-NNNN-<slug>.png     # renderer output for the same screen
```

The project chooses the visual system and screenshot renderer. Do not copy a
reference project's framework, component library, or machine-local paths into
an adopting repository.

## When to Use

Use this skill when a material change adds or changes a primary screen, pane,
dialog, or multi-step interaction used by a human operator, end user, or
administrator.

Do not use it for invisible server behaviour, APIs, configuration-only changes,
or a minor cosmetic adjustment that does not alter interaction, hierarchy, or
meaning. When uncertain, include the wireframe: it is cheaper than shipping an
unreviewed workflow.

## Contracts

- Every CAP declares `**Primary surface:** human` or `none`. Each human-facing
  CAP has exactly one manifest screen; a `none` CAP has none. Require the manifest,
  generator, and index whenever any human-facing CAP or the wireframe directory
  exists. Do not create empty directories just to activate the workflow.
- One screen has one stable CAP ID. Name HTML and PNG files
  `CAP-NNNN-<slug>` to match the capability record.
- `docs/product/wireframes/generate.mjs` is the
  only editable screen-definition source. It produces the HTML, `index.html`,
  and `manifest.json`; do not hand-edit those generated outputs.
- HTML is the portable review source; PNG is a renderer export of that same
  HTML at the manifest viewport. `manifest.json` inventories the stable CAP ID,
  non-empty title, HTML path, PNG path, and positive integer viewport width/height
  for every screen. IDs are unique, HTML/PNG names match, and both on-disk
  artifact directories agree with the manifest in both directions.
- `index.html` links every screen. Each qualifying CAP links its matching HTML
  and PNG under a `## Links` section.
- Wireframes illustrate the intended interface. They are not implementation,
  executable evidence, or a replacement for the CAP's falsifiable behaviour
  and tests.
- Use synthetic, non-sensitive sample content. Never place real identities,
  credentials, tokens, or production data in a screen or export.
- Preserve the adopting product's established visual language. If none exists,
  establish a small shared shell and reusable primitives before adding screens;
  do not make every CAP page a separate visual design.

### Proposal-to-capability handoff

- **Pending CHG:** Read both product and change DOX plus the wireframe child if
  present before selecting a destination. Put design sources, HTML, screenshots,
  and prose in `docs/changes/reviews/CHG-<number>/`. Its `README.md` declares
  `**Status:** review-only` and links the artifacts; the owning CHG links that
  README. Never put loose assets in active/archive directories, allocate a future
  CAP ID, add a proposal to the product manifest, or link review files from a CAP.
- **Implementation slice:** Create or update the CAP and its canonical screen
  definition, including when changing an existing CAP. Regenerate inventory,
  index, and HTML, render PNG, and link both outputs under the CAP's `## Links`
  in the same slice as the primary surface and behavior tests. Do not simply move
  or rename proposal files into the product directory.
- **Closure:** Keep review packages at their same paths as frozen review-only
  receipts for done/cancelled CHGs. Repair links when archiving the owner; remove
  the package if its owner is removed. Follow `docs/changes/README.md` for ownership.
- **Pencil relationship:** A Pencil file may be retained as an upstream visual
  design source or review record. It never replaces the repository-owned HTML
  generator and PNG export for an implemented CAP.

## Procedure

1. **Classify the surface.** In the active CHG, identify the primary screen and
   the task it enables. State data, permission, and failure boundaries in the
   CHG while pending, then in the CAP once implementation begins; represent
   their visible consequences in the wireframe.
2. **Use the correct lifecycle boundary.** Keep pre-implementation visual work
   in the CHG review package. In the implementation vertical slice, add or update the
   CAP-linked screen before runtime UI work. Show the normal state, controls,
   hierarchy, relevant empty/error/permission state, and the action that
   completes or blocks the task. Do not turn the page into a prose copy of the
   CAP.
3. **Generate deterministic artifacts.** Keep screen definitions and shared
   layout in the repository-owned generator. Regenerate `html/`, `index.html`,
   and `manifest.json`; render the matching PNG into `exports/`. Do not
   hand-edit generated outputs.
4. **Link the capability.** Add both relative paths in the CAP's `## Links`
   section. Update `docs/product/README.md` with the wireframe index when the
   repository adopts the feature for the first time.
5. **Keep it current.** When a later CAP change alters interaction, information
   hierarchy, visibility, or a user-observable failure state, update the screen
   and PNG in the same change. Do not churn wireframes for internal refactors.

## Verification

- `manifest.json` enumerates every `html/CAP-*.html` and
  `exports/CAP-*.png` pair.
- `index.html` links every manifest screen.
- Every qualifying CAP has valid relative links to its HTML and PNG artifacts.
- The generated HTML opens without a project build step, and the PNG is a
  current rendering of that HTML.
- Review packages retain a linked review-only README and an owning CHG, stay
  outside product CAP links and the manifest, and do not claim unimplemented CAPs.
- The visual handoff gate runs generation and rendering and inspects the result.
  Structural validation cannot prove render freshness, approval, or honest
  primary-surface classification.
- Run the project's product-record validation and the affected behaviour tests.

## Pitfalls

- Do not treat a polished wireframe as proof that authorization, validation, or
  privacy behaviour exists. The implementation and behaviour tests prove it.
- Do not render only the happy path when an empty, denied, validation, or
  destructive state changes what a person can safely do.
- Do not maintain HTML and PNG manually as independent artifacts; they drift.
- Do not require a wireframe for a feature with no primary human-facing
  surface.
