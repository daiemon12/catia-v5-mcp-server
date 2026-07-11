# GSD (Generative Shape Design) Extension — Implementation Plan

**Status as of 2026-07-11:** Stages 1–6 below are **coded but not yet verified against
live CATIA**. This document is the durable, portable version of the plan — written so
work can continue from a fresh session or a different tool (e.g. Codex) without the
originating conversation's history. See [`DEPLOYMENT.md`](DEPLOYMENT.md) for how to
reach the running CATIA instance and exercise these tools.

## Goal

The base server (`catia_mcp/tools/part_design.py` etc.) only wraps solid Part Design
via `body.ShapeFactory` — pads, pockets, shafts, fillets, patterns. That's sufficient
for prismatic/revolved mechanical parts (brackets, housings, shafts) but cannot produce
sculpted, styled geometry — the concrete motivating case was **a production-style
automotive wheel**, whose spokes require lofted/blended surfaces, not sketch-extrudes.

This extension adds a parallel path through CATIA's **Generative Shape Design (GSD)**
API — `part.HybridShapeFactory` and geometrical sets (`HybridBody`) — plus
surface-to-solid conversion, advanced fillets, and Knowledgeware formulas.

**Ceiling, stated honestly:** this authors **manufacturable, styled geometry**. It does
not reach Class-A surface quality (G2/G3 continuity is an interactive styling craft) or
engineering sign-off (GD&T, DFM, FEA/fatigue). Scope "production-ready" to
"manufacturable," not "released."

## Architecture decision: extend, don't replace

Two live implementations existed at the time of planning:
1. **This server** — low-level `mcp.server.Server`, class-based tool modules
   (`get_tool_definitions()` + `execute()`), raw `win32com.client` COM automation.
   Already deployed and running against a real CATIA instance (see DEPLOYMENT.md).
2. **[`tongriyaotxt/catia-mcp`](https://github.com/tongriyaotxt/catia-mcp)** — a
   `FastMCP` server with standalone functions, `pycatia`-backed, that turned out to
   already implement most of the GSD primitives this plan needed.

**Decision:** keep this server as the base (it's deployed and hardened — HTTP
transport, token auth, offline install already solved) and **port the reference
project's COM logic into this server's module pattern**, rather than adopting the
reference server wholesale.

**What actually got built differs slightly from that plan**: the ported tools use
**raw `win32com` late-binding** via `connection.py`'s `hybrid_shape_factory` /
`shape_factory` properties, not the `pycatia`-wrapped `HybridShapeFactory` the
reference project used. `pycatia` is listed in `pyproject.toml` and there's an unused
`CATIAConnection.pycatia_part_document()` accessor, but **no tool module currently
calls it** — the GSD tools work with `mcp` + `pywin32` alone. This matters
operationally: the deployed CATIA box does not have `pycatia` installed, and (as far
as the code shows) doesn't need it.

## Reuse assessment — `tongriyaotxt/catia-mcp`

A code-level review (not just the README) found working implementations for nearly
every surfacing primitive this plan needed:

| Plan stage | Status | Reference source | Covered |
|---|---|---|---|
| References/selection | partial | `selection.py` | Name lookup + face/edge by index with fallback. Does **not** solve robust geometric-query selection — see Open Work below. |
| Wireframe | reuse | `gsd.py`, `gsd_advanced.py` | point/line/plane/project/intersect/parallel-curve/spine; helix with a **locale-safe spline fallback** (relevant — the deployed CATIA is Russian-locale). |
| Surfaces | reuse | `gsd.py`, `gsd_advanced.py` | extrude/revol/offset/sweep/fill/blend/join/trim/split/boundary + **multi-section loft** (the spoke-skin primitive) and extrapolate. |
| Surface → solid | reuse | `part_design_advanced.py` | `add_new_close_surface`, `add_new_thick_surface`, `add_new_sew_surface`. |
| Advanced fillets/draft | partial | `part_design_more.py` | face fillet, tritangent fillet (index-based faces). Variable-radius fillet and reflect-line draft still to add. |
| Knowledgeware | reuse | `parameters.py` | `add_parameter`, `add_formula` → `create_formula`. Design table is the one gap. |

**License note:** the reference repo declares MIT in `pyproject.toml` and its README
but **ships no `LICENSE` file**. Both projects are MIT, so intent is compatible, but
before this code goes anywhere beyond private storage, get a formal `LICENSE` from the
author or otherwise document provenance clearly (this file is that documentation for
now — see the `README.md` Credits section, which also carries this note).

## What's implemented (module inventory)

All modules follow the existing pattern: a class with `get_tool_definitions()` +
`execute()`, constructed with the shared `CATIAConnection`. Reference resolution for
all of them goes through `catia_mcp/tools/_geometry.py`'s `GeometryContext`, which
centralizes active-geoset tracking, name-based lookup (`selection.Search(f"Name={name},all")`),
and reference creation.

### `geoset.py` — geometrical sets & reference plumbing
`catia_new_geoset`, `catia_list_geosets`, `catia_set_active_geoset`,
`catia_select_reference`, `catia_list_subelements`

### `wireframe.py` — 3D wireframe (the spoke skeleton)
`catia_point_coord`, `catia_point_on_curve`, `catia_line_pt_pt`, `catia_plane_offset`,
`catia_plane_normal`, `catia_plane_three_points`, `catia_project`, `catia_intersect`,
`catia_corner`, `catia_connect_curve`, `catia_helix` (with Russian-locale fallback)

### `surface.py` — surfaces (the spoke skin)
`catia_extrude_surface`, `catia_revolve_surface`, `catia_sweep`, `catia_loft`,
`catia_fill`, `catia_blend`, `catia_join`, `catia_split_surface`, `catia_trim`,
`catia_offset_surface`, `catia_extrapolate`

### `part_design_advanced.py` — surface → solid, advanced fillets
`catia_close_surface`, `catia_thick_surface`, `catia_sew_surface`, `catia_split_solid`,
`catia_face_fillet`, `catia_tritangent_fillet`, `catia_variable_fillet`,
`catia_advanced_draft`

### `knowledge.py` — parametric family
`catia_create_parameter`, `catia_create_formula`, `catia_create_design_table`

### `wheel.py` — composite orchestration tool
`catia_design_wheel` — a single high-level tool taking `rim_diameter`, `rim_width`,
`offset`, `pcd`, `bolt_count`, `center_bore`, `spoke_count`, `spoke_style`
(`"simple_lofted"` only, currently), plus manufacturing defaults (hub thickness,
flange height, rim/spoke thickness, draft angle, fillet radius, valve/lug hole
diameters, material density) and export options. Intended to chain the primitive
tools above into one call for the common case.

**Total registered tools:** 63 across all modules (verify with `tools/list` — see
DEPLOYMENT.md for how to query the live server).

## Open work

1. **Live verification — nothing above has been run against real CATIA yet.**
   This is the immediate next step (tracked as the "smoke test" in project history).
   Start small: `catia_new_geoset` → `catia_point_coord` ×2 → `catia_line_pt_pt` →
   confirm it appears in CATIA's spec tree. Then attempt one surface (`catia_extrude_surface`
   or `catia_loft`) and one surface→solid conversion (`catia_close_surface`). Expect
   friction — the reference code has multiple "may not work in this locale/version"
   caveats and best-effort fallbacks (see the helix implementation for the pattern to
   follow: try the native feature, catch, fall back to a manual construction).

2. **Robust reference selection is still the real gap.** `GeometryContext.find_object()`
   resolves by exact `Name=` match via `Selection.Search`. This works for named
   features but not for "the face whose normal points +Z" or "the nearest edge to this
   point" — the kind of query that fillet/draft/blend operations need when the target
   doesn't have (or CATIA doesn't expose) a stable name. This is the one piece the
   reference project didn't solve either. Until it's addressed, expect wheel-building
   to require manually naming/tracking every intermediate feature rather than querying
   geometrically.

3. **Design table** (`knowledge.py`) is the one Stage-6 gap — formulas exist, a
   spreadsheet-driven variant table doesn't yet.

4. **Wheel spoke styles**: `catia_design_wheel`'s `spoke_style` enum currently only
   accepts `"simple_lofted"`. Expanding the family (turbine, mesh, multi-spoke twin)
   is straightforward once the loft path is verified — it's a matter of generating
   different guide-curve geometry, not new CATIA API surface.

5. **End-to-end wheel build.** Once 1–2 above are solid, run `catia_design_wheel` (or
   its constituent calls) against live CATIA, inspect the result, and iterate. This is
   the real proof of the whole extension.

## Risks

- **Reference selection is the whole game** (see Open Work #2). This is where scripted
  surface modeling typically breaks; budget real time here before trusting anything
  downstream of it.
- **Ported code is unproven on this install.** Every tool needs a live smoke test
  against the actual Russian-locale CATIA — the porting was fast; the validation is
  the work.
- **Late-binding signature drift.** `AddNew*` argument order and enum values vary
  across CATIA V5 releases/service packs. Validate each against `V5Automation.chm` on
  the target install if a call fails with an unexpected COM error.
- **License provenance** on the ported code (see Reuse Assessment above) — resolve
  before wider distribution.
- **The Class-A / production ceiling stands** — see Goal section. Don't let "it built
  a solid" be mistaken for "ready to manufacture."
