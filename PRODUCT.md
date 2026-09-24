# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

PathGen serves Grade 7 students following a fixed adaptive mathematics journey, teachers monitoring currently assigned classes, and administrators managing accounts, classes, global access, audit history, and research oversight within their distinct authorization scopes.

## Product Purpose

PathGen provides an accessible, auditable learning path from pre-test through post-test. It preserves assessment evidence, keeps adaptive decisions explainable, and supports honest matched pre/post research reporting without allowing management tools to rewrite learning evidence.

## Positioning

PathGen separates assessment evidence, BKT mastery estimation, deterministic Daddy Chill routing, and grounded feedback so every learning transition remains reviewable without letting generated feedback control scoring or access.

## Operating Context

The product is a server-rendered Django application backed by PostgreSQL and deployed as one Railway service. Administrators use account, class, access, and audit tools; teachers read assigned-class monitoring signals; students complete a one-question-at-a-time path. Class membership supports monitoring only and never gates student learning.

## Capabilities and Constraints

- Roles are `admin`, `teacher`, and `student`, with server-side role and object-scope enforcement.
- Student Study Access affects students only; Post-test Access is an additional global gate and never replaces path eligibility.
- Reversible lifecycle actions are normal. Protected learning and audit history cannot be destructively cascaded.
- The interface is permanently light-mode and uses Django templates, Tailwind, Preline behavior, self-hosted Geist, and Lucide icons.
- Phase work follows the canonical documentation and build order; later-phase curriculum, session, adaptive-engine, RAG, and research dashboard implementation must not be pulled forward.

## Brand Commitments

The product name is PathGen. The approved cyan/neutral light theme and semantic tokens in the canonical theme are binding. Role avatars are jellyfish for students, turtle for teachers, and octopus for administrators, and are not user-editable.

## Evidence on Hand

The canonical requirements, policy values, navigation, modal behavior, data contract, theme, and phased acceptance criteria live in `../pathgen2.0docs/`. Phase 4 has no approved charts, metrics, or curriculum content to present, so the admin dashboard remains a truthful shell rather than fabricating data.

## Product Principles

- Protect evidence and preserve an auditable reason for sensitive changes.
- Keep learning access independent from classroom monitoring structure.
- Make each role's next authorized task clear without exposing unavailable actions.
- Prefer complete server-rendered states with progressive enhancement.
- State limitations honestly and never fabricate research meaning.

## Accessibility & Inclusion

Target WCAG 2.2 AA-oriented practices: semantic landmarks, keyboard operation, visible focus, focus-managed dialogs and drawers, 44px touch targets, associated error summaries, zoom/reflow, non-color state meaning, and reduced-motion support.
