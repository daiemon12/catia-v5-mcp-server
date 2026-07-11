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

1. **Live verification — first smoke test run 2026-07-11, partial success.**
   Ran against the real (Russian-locale) CATIA deployment (see `DEPLOYMENT.md`):
   `catia_new_part` → `catia_new_geoset` → `catia_point_coord` ×2 → `catia_line_pt_pt`
   **all succeeded** and produced real features in CATIA's spec tree. `catia_extrude_surface`
   **failed** with a COM type-mismatch (`-2147352571`, decoded from Russian:
   "Type mismatch") — **root cause and fix below, already applied**. Continue the
   smoke test from `catia_extrude_surface` onward: `catia_loft` (the spoke-critical
   primitive) and `catia_close_surface` (surface→solid) are still completely
   unverified. Expect similar argument-shape issues — see the pattern below before
   assuming a given `AddNew*` call is a straight port.

   **Root cause found & fixed:** `AddNewExtrude`'s 4th parameter must be a CATIA
   `HybridShapeDirection` object, not a `Reference`. The initial port resolved
   `direction` through the generic `GeometryContext.resolve()` (which builds a
   `Reference` via `CreateReferenceFromObject`) — passing a plane *reference* where
   CATIA wants a *direction vector* throws exactly this type mismatch. Fixed by adding
   `GeometryContext.direction()` (`_geometry.py`), which builds a proper direction via
   `hsf.AddNewDirectionByCoord(x, y, z)` from either `"xy"/"yz"/"zx"` shorthand or an
   explicit `{"x":, "y":, "z":}` vector, and wiring it into `catia_extrude_surface`'s
   `direction` argument (its input schema changed accordingly — no longer accepts an
   arbitrary reference). **This exact bug — a `Reference` passed where CATIA wants a
   `Direction`/vector object — is a strong candidate to recur in any other tool built
   the same way**; if `catia_sweep`, `catia_helix`, or similar throw a type-mismatch
   COM error, check for this pattern first before assuming something more exotic.
   `catia_revolve_surface`'s `axis` argument was checked and is *not* affected — a
   revolve axis is legitimately a line `Reference` in the real API.

2. **Base-server bug found via the smoke test, not GSD-specific: `body.ShapeFactory` is
   wrong.** After the extrude fix, `catia_close_surface` failed with `<unknown>.ShapeFactory`
   — a pywin32 dynamic-dispatch AttributeError, not a COM call error. Isolated by
   testing `catia_pad` (an original, pre-GSD tool, never previously smoke-tested) in
   the same session: **identical failure**. `ShapeFactory` is a property of `Part`, not
   `Body` — `Body` only exposes `Shapes`/`Sketches` (which is why `catia_list_features`,
   using `body.Shapes`, worked fine on the same object). This affected **13 call sites
   in `part_design.py`** (every solid feature: pad, pocket, shaft, groove, fillet,
   chamfer, hole, patterns, mirror, shell, draft, thickness) **plus 3 in `wheel.py`**
   plus the shared `CATIAConnection.shape_factory` property — i.e. most of the base
   server's advertised solid-modeling functionality had never actually been exercised
   against live CATIA before this session and was non-functional. Fixed: all sites
   changed to `part.ShapeFactory`. **Verified live 2026-07-11 after redeploy**:
   `catia_pad` now succeeds (produces a real feature, confirmed via `catia_list_features`);
   `catia_close_surface` now reaches CATIA's actual solver (`AddNewCloseSurface`) and
   fails only on deliberately-invalid test geometry (an infinite plane isn't a closed
   volume boundary) — the `AttributeError` is gone. Both fixes hold.

3. **`catia_design_wheel` geometry bug: hub/spoke sketch self-intersects.** First
   live attempt got through document/parameters/rim phases (confirming `Feature.Name`
   *is* writable — only `Part.Name` isn't, see #4 below) then failed on the hub/spoke
   pad's `UpdateObject` with a generic COM error. Root cause: the spoke-arm quad
   profile used `r1 = hub_radius * 0.75` as its near-hub radius, but each corner point
   is additionally offset tangentially by `spoke_thickness/2`, so its true distance
   from the origin is `hypot(r1, half)` — with the `*0.75` factor this landed well
   *inside* the hub circle (e.g. hub_radius=71.15 → corner at ~54mm), producing a
   self-intersecting sketch profile that CATIA's Pad solver rejects outright (with no
   useful diagnostic beyond a generic COM error — this class of failure gives no hint
   it's a geometry problem specifically; verify by computing the actual corner
   distances by hand, as done here, when `UpdateObject` fails on a Pad/Pocket).
   **Fixed**: `r1 = hub_radius` (spokes now start flush with the hub's outer edge,
   `hypot(r1, half) >= hub_radius` always holds). **Not yet re-verified live** — the
   subsequent bore/lug pocket phase is also still completely untested.

4. **`Part.Name` is read-only on this CATIA configuration; `Sketch.Name`/`Feature.Name`
   are not.** `catia_design_wheel`'s first live attempt failed immediately on
   `doc.Part.Name = ...`. Confirmed on retest that renaming a `Pad` feature
   (`rim.Name = "Rim_Barrel"`) succeeds fine — this is specific to `Part`, not a
   broader "renaming doesn't work" issue. Fixed with a best-effort `_try_rename()`
   helper in `wheel.py`, applied to all six rename call sites there (only the `Part`
   one actually needed it, but guarding the rest was cheap insurance against burning
   another redeploy cycle on the same failure class).

5. **Robust reference selection is more built-out than initially assessed** — revise
   downward as a risk. `GeometryContext.resolve()` (`_geometry.py`) already supports
   geometric-query selection: pass `{"feature": "...", "kind": "face", "nearest_point":
   [x,y,z]}` or `{"kind": "face", "normal": [x,y,z]}` and it scores candidate
   sub-elements via `SPAWorkbench.GetMeasurable()` (center-of-gravity distance /
   normal-vector dot product) rather than requiring an exact name or index. This
   covers a meaningful chunk of what the original plan called "the one genuinely new
   piece to build." **Still unverified against live CATIA** (only read, not executed;
   `SPAWorkbench` availability/behavior on this CATIA release/locale is unconfirmed) —
   prioritize testing this path specifically, e.g. resolve a fillet edge by proximity
   instead of by index, before assuming it's solid. If it works, most of the original
   Stage-1 concern is already resolved by existing code, not new work.

6. **Design table** (`knowledge.py`) is the one Stage-6 gap — formulas exist, a
   spreadsheet-driven variant table doesn't yet.

7. **Wheel spoke styles**: `catia_design_wheel`'s `spoke_style` enum currently only
   accepts `"simple_lofted"`. Expanding the family (turbine, mesh, multi-spoke twin)
   is straightforward once the loft path is verified — it's a matter of generating
   different guide-curve geometry, not new CATIA API surface.

8. **End-to-end wheel build — DONE. First wheel solid built and saved live,
   `"status": "complete"`.** Sequence of live attempts against a real 400mm/5×114.3
   wheel spec, each fixing the failure the previous one surfaced: (1) `Part.Name`
   read-only → fixed; (2) hub/spoke self-intersection → fixed; (3) all five build
   phases succeeded (document, parameters, rim, hub_and_spokes, mounting_features);
   (4) `SaveAs` succeeded — a real CATPart on disk
   (`C:\catia-mcp-setup\output\SmokeWheel5.CATPart`); (5) STEP export and (6)
   measurement failed on the `GetWorkbench` bug (item 9) and were made non-fatal;
   (7) full run confirmed `"status": "complete"` with `catpart_path` populated.
   STEP export and mass/volume measurement still don't work
   (STEP: likely a missing interoperability license, not a code bug, still failing
   after the GetWorkbench fix since it's an unrelated ExportData failure; measurement:
   should now work post-item-9-fix, not yet reconfirmed). **The wheel geometry itself
   — rim, hub, spokes, bore, lug holes, parametrically driven — is proven working.**
   Remaining before this is a complete pipeline: confirm measurement now succeeds,
   decide whether STEP export matters enough to chase (may just need a license), and
   move on to styling (fillets/draft, currently explicitly out of scope per the
   tool's own warnings) and the loft-based spoke styles (item 7).

9. **Fixed: `GetWorkbench` belongs on `Document`, not `Application`.** Same class of
   mistake as item 2 (`body.ShapeFactory` vs `part.ShapeFactory`). Isolation test
   confirmed it was general, not wheel-specific: `catia_get_inertia` (an original,
   unmodified, pre-GSD tool) threw the identical `CATIA.Application.GetWorkbench`
   error when called directly. Fixed all 5 call sites — `measurement.py` (3),
   `_geometry.py`'s `_choose_subelement()` (1), `wheel.py`'s `_measure()` (1) — from
   `self.conn.app.GetWorkbench(...)` to `self.conn.active_document.GetWorkbench(...)`.
   **Not yet re-verified live.** If this holds, it resolves the last known issue in
   the measurement tools and unblocks live-testing the geometric-query selection path
   (item 5).

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
