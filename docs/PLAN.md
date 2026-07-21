# GSD (Generative Shape Design) Extension — Implementation Plan

**Status as of 2026-07-19:** Stages 1–6 below are **coded but not yet verified against
live CATIA**. This document is the durable, portable version of the plan — written so
work can continue from a fresh session or a different tool (e.g. Codex) without the
originating conversation's history. See [`DEPLOYMENT.md`](DEPLOYMENT.md) for how to
reach the running CATIA instance and exercise these tools. Deployment host moved to
`192.168.5.42` and a fidelity gap-analysis against a real wheel drawing was added
(items 12-13 in Open Work). The barrel/loft/valve fidelity items are done and verified
live; the styling phase (item 14, casting draft and spoke-root fillets) is delivered
and QA'd; drawing tools (item 15) and a second spoke style (item 16, `y_fork`) are also
done and verified live. **All items below (1-16) remain an accurate record of the
GSD/wheel work** — nothing in this stage regressed.

**Scope note (added 2026-07-19):** this server has since grown a large, separate body
of code — `catia_mcp/tools/contest.py` (15 tools: `catia_solve_task07_plug` /
`catia_solve_task09_eviscerator` / `catia_solve_task11_geosets` /
`catia_solve_task12_hex_prisms` / `catia_solve_task13_chain` /
`catia_solve_task15_centerline` / `catia_solve_task16_isolate_green` and matching
`catia_taskNN_report` tools), plus contest-specific tools bolted onto
`assembly.py` (`catia_rebuild_task02_product`), `measurement.py`
(`catia_task06_debug_guides`), and `document.py` (`catia_close_document_by_path`), plus
`catia_mcp/tools/saw.py` (`catia_design_circular_saw` — its own `DEFAULTS` default to a
`CATIA_2026_LADUGA\08\...` path, confirming it's a contest-task solver, not a
general-purpose GSD primitive). **This is the CATIA_2026_LADUGA contest-solving
initiative** (see the user's own task-folder rules — tracked outside this repo's docs,
not in PLAN.md) and is **intentionally out of this document's scope**: it shares
nothing with the wheel/GSD surfacing work below and isn't mentioned further here. It's
called out only so the tool counts elsewhere in this file (and in `README.md`, which is
separately stale) aren't mistaken for GSD-only numbers — see the note on tool counts in
the module inventory below.

All of that landed in one commit (`9be2035`, "feat: add parametric circular saw blade
builder for CATIA V5") whose message describes only the saw blade builder but whose
diff also added `contest.py` in full and touched `assembly.py` (+650 lines),
`document.py` (+94), `drawing.py` (+314), `knowledge.py` (+162), `measurement.py`
(+439), `part_design.py` (+427), and `part_design_advanced.py` (+118) — worth knowing
if bisecting a regression in any of those files turns up this commit; the diff is far
larger than the message suggests. It did not touch `wheel.py` or the core
wireframe/surface GSD modules, so it has no bearing on items 1-16 above.

Two of the files it touched did gain genuinely GSD-relevant tools alongside the
contest-scoped growth, and those ARE in scope for this document — folded into the
module inventory below: `catia_build_slinky_from_points` (`part_design_advanced.py`)
and `catia_fill_drawing_bom` (`drawing.py`). The BOM tool was live-verified on
2026-07-21; the slinky tool was live-verified the same day with
`python scripts/smoke_slinky.py`: a 49-point, three-turn guide produced an explicit
sweep and a closed solid, and the temporary CATPart was closed without saving.

A remote-restart helper now exists and is **live-verified (2026-07-14)**:
[`scripts/restart_remote_catia_mcp.ps1`](../scripts/restart_remote_catia_mcp.ps1)
restarts the interactive-session MCP server over WinRM. On this host the direct
`CreateProcessAsUser`/`CreateProcessWithTokenW` path fails (error 1314, required
privilege not held) and it falls back to a one-shot LocalSystem launcher service —
that fallback is the normal path every restart takes unless the WinRM account is
granted `SeAssignPrimaryTokenPrivilege`. See DEPLOYMENT.md for the full shape.

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
`catia_advanced_draft`, `catia_build_slinky_from_points` (added since — builds a solid
slinky spring from explicit guide points + a circular wire profile; **live-verified
2026-07-21**, see the scope note above)

### `knowledge.py` — parametric family
`catia_create_parameter`, `catia_create_formula`, `catia_create_design_table`,
`catia_copy_parameter_as_link`, `catia_list_relations`, `catia_upsert_formula` (the
design table was live-verified 2026-07-21; the latter three were added since and are
not individually live-verified)

### `wheel.py` — composite orchestration tool
`catia_design_wheel` — a single high-level tool taking `rim_diameter`, `rim_width`,
`offset`, `pcd`, `bolt_count`, `center_bore`, `spoke_count`, `spoke_style`
(`"simple_lofted"` only, currently), plus manufacturing defaults (hub thickness,
flange height, rim/spoke thickness, draft angle, fillet radius, valve/lug hole
diameters, material density) and export options. Intended to chain the primitive
tools above into one call for the common case.

**Total registered tools:** 63 at the time this line was first written; the server now
registers 136 (verify with `tools/list` — see DEPLOYMENT.md for how to query the live
server). The 63→136 growth is **not** all GSD work: about 21 of those tools
(`contest.py`'s 15, plus `catia_design_circular_saw`, `catia_rebuild_task02_product`,
`catia_task06_debug_guides`, `catia_close_document_by_path`, and the two additions
folded into the inventory above) belong to the CATIA_2026_LADUGA contest-solving
initiative described in the scope note at the top of this document, not to the GSD/wheel
extension this plan tracks.

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

6. **Design table — DONE.** `catia_create_design_table` was live-verified on
   2026-07-21 with `python scripts/smoke_design_table.py`: a temporary CATPart bound
   `Wheel_Diameter` and `Spoke_Count` to an external table, and
   `catia_list_relations` confirmed the resulting `DesignTable` relation.

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
   **Verified live**: `catia_get_inertia` no longer errors.

10. **Fixed: `Measurable.Volume`/`.Area`/`GetBoundingBox`/`GetMinimumDistance` return
    SI base units (m³/m²/m), not mm³/mm²/mm — every measurement tool was silently
    wrong by 1e9/1e6/1000×.** Found immediately after item 9's fix: `catia_get_inertia`
    on a 10mm-radius × 5mm pad returned `area_mm2: 0.0009` instead of ~942. Verified by
    hand: 942.48 mm² × 1e-6 = 0.00094248 m² → rounds to exactly `0.0009` — confirms the
    raw value is genuinely in m², just mislabeled. Same math confirmed for volume. This
    also explains why the wheel's first successful `measurements` looked like garbage
    (`mass_kg: 2.6e-08`) — reinterpreting the raw `volume_mm3` field as m³ gives ~9.7
    liters, a plausible mass (~26kg unoptimized aluminum blank) for a conservative solid
    wheel with no back-cavity removal. Fixed all four affected call sites
    (`_measure_distance`, `_get_inertia`'s volume/area/COG, `_get_bounding_box`,
    `wheel.py`'s `_measure`) with explicit ×1000/×1e6/×1e9 conversions; verified the
    conversion round-trips correctly against hand-computed geometry before deploying.
    **Verified live**: the same 10mm/5mm test pad now returns `volume_mm3: 1570.7963`
    and `area_mm2: 942.4778` — matching the hand-computed expectation (1570.80 /
    942.48) to 4 decimal places. The wheel's `measurements` are now sane too:
    `volume_mm3: 9,689,826` (9.69 L) / `mass_kg: 26.16` — exactly matching the estimate
    made when this bug was first found.

    **New, separate issue found while verifying this fix**: `catia_get_bounding_box`
    now fails with `GetMeasurable.GetBoundingBox` (same terse, no-COM-tuple error
    shape as the other dynamic-dispatch bugs). Investigated fully in item 11 below —
    resolved as "not fixable," not "not yet fixed."

11. **Resolved (not a bug): `GetBoundingBox` and `GetInertia` do not exist on
    `Measurable` — CATIA's Automation API has no such methods.** Three redeploy cycles
    tried increasingly specific hypotheses for item 10's `GetBoundingBox` failure: (a)
    `VT_BYREF|VT_ARRAY|VT_R8` SAFEARRAY, (b) `VT_BYREF|VT_ARRAY|VT_VARIANT` SAFEARRAY,
    (c) two separate 3-element arrays instead of one 6-element array. **All three
    failed with the byte-for-byte identical error text.** That uniformity is itself
    the diagnostic: if the problem were argument type or count, changing either
    should have changed the failure. An identical error regardless of what's passed
    means the call never gets past member resolution — the same failure *shape* as
    the `ShapeFactory`/`GetWorkbench` "wrong object" bugs (items 2, 9), but this time
    there's no right object to move it to.

    Confirmed by installing `pycatia` locally (already a declared dependency; this
    needed no CATIA connection, just reading its source — a comprehensive wrapper of
    CATIA's real CAA V5 interfaces, built from official VBA documentation) and
    grepping the entire package: `GetBoundingBox` and `GetInertia` do not appear
    **anywhere** in pycatia, not even in a docstring. `Measurable`'s complete method
    list (`pycatia/space_analyses_interfaces/measurable.py`) has `volume`, `area`,
    `length`, `get_cog`, `get_plane`, `get_minimum_distance`, etc. — but no bounding
    box or inertia matrix. The real inertia matrix lives on a **separate `Inertia`
    object** (`SPAWorkbench.Inertias.Add(ref)` → `.GetInertiaMatrix()`,
    `.mass`, `.density`, `.get_cog_position()`), not on `Measurable` at all — the
    original ported code called a plausible-sounding but nonexistent method.
    No genuine bounding-box capability was found anywhere pycatia covers
    (checked `Selection`, drawing views, arrangement interfaces — none fit).

    **Also found and fixed while cross-referencing pycatia's source**: `GetPlane`'s
    real signature (confirmed from CAA V5's own VB help, quoted in pycatia's
    docstring) is **one 9-element array** — origin xyz(0:3), first in-plane direction
    xyz(3:6), second in-plane direction xyz(6:9) — not the two separate 3-element
    `(origin, direction)` arguments `_choose_subelement`'s `normal`-based scoring was
    calling it with. This was a latent bug never exercised live (no test had used
    `normal`-based selection yet). Fixed the arity **and** a geometric error the old
    code would have had even with correct arity: the two `GetPlane` outputs are the
    plane's own in-plane basis vectors, not its normal — using either directly as "the
    normal" is backwards (in-plane vectors are perpendicular to the actual face
    normal). The true face normal is `direction1 × direction2` (cross product); now
    computed explicitly before scoring.

    **Resolution**: `catia_get_bounding_box` now raises a clear, honest error
    explaining the API limitation instead of a cryptic COM-shaped one.
    `wheel.py`'s `_measure()` no longer attempts the doomed call at all — removed
    rather than left as a silently-always-failing try/except. `GetPlane`'s arity/
    cross-product fix is a real, high-confidence bug fix, live-untested as of this
    commit. A genuine bounding box, if ever needed, requires new code (enumerate
    vertices via `Topology.Vertex` search — the same pattern `list_subelements`
    already uses — and take coordinate min/max), not a different argument shape to
    an existing call; not pursued now since nothing in Phase 2/3 requires it.

    **Not fixed, flagged only**: `_geometry.py`'s `_choose_subelement()` also calls
    `measure.GetCOG`/`GetPlane` for `nearest_point`/`normal`-based sub-element scoring
    and has the same raw-meters values feeding a millimeter-scale comparison. Left
    alone because the scoring is relative (picks the *minimum*-distance candidate), and
    a uniform unit-scale error doesn't change which candidate wins — but if that
    function's absolute distances are ever surfaced to a caller, they'd be wrong by the
    same 1000× factor. Worth fixing for correctness/clarity even though it doesn't
    currently produce a wrong *selection*.

12. **`catia_design_wheel`'s geometry is far simpler than a real production wheel
    drawing** — found 2026-07-13 while checking the tool against a sample
    front-view/side-view technical drawing (10-spoke cast wheel, JWL-style barrel
    cross-section). Concrete gaps, in priority order for closing them:
    - **Barrel/bead-seat profile is now verified live against `.42` (2026-07-14).**
      [`wheel.py`'s rim phase](wheel.py) creates a closed YZ cross-section and
      revolves it around a construction centerline with `Shaft`. The parameterized
      profile includes front/rear flange transitions, bead seats, safety humps, a
      drop-center well, and a uniform radial wall. Live checks completed:
      `Sketch -> CenterLine -> Shaft` smoke passed after fixing the read-only
      `FirstAngle` assignment; a full `catia_design_wheel` build completed and saved
      on `.42` using the legacy call shape (no new arguments required); and a
      separate 300-degree rim-only `Shaft` screenshot visually confirmed the bead
      seats, humps, and drop-center on an open segment. This first version remains
      intentionally segment-based; production flange/bead-seat radii and final
      topology-dependent fillets are still future styling work. Additional live
      limitations discovered during verification:
      `catia_design_wheel` could previously block CATIA with a `SaveAs` modal if the
      same output CATPart was already open in the session (a fail-fast guard is now
      deployed and active, though the duplicate-path case has not been deliberately
      re-triggered live after the latest restart), and `catia_screenshot` currently
      writes EMF content even when a `.png` path is requested, so screenshot files
      need EMF consumers or a post-conversion step until that tool is corrected.
    - **Spoke crown loft is now implemented and verified live against `.42`
      (2026-07-14).** The flat `Simple_Lofted_Spoke_Web` pad was replaced by three
      closed 3D-spline sections (hub/root, crowned mid-section, and narrowed rim
      section) coupled by matching vertices and two guide splines. The GSD skin is
      capped with two `Fill` surfaces, assembled with `Join`, converted by
      `CloseSurface`, and replicated by a Part Design circular pattern. The hub is
      added after the pattern so every Part Design operation remains a connected
      solid. Live debugging established that closed 2D sketches on offset planes did
      not solve as loft sections on this CATIA install, while equivalent closed 3D
      splines did; a bare loft is not watertight and cannot be passed directly to
      `CloseSurface` without the two caps and join.

      A legacy-shape `catia_design_wheel` call (no new spoke arguments) completed and
      saved `MCP_Wheel_Lofted_Spokes_20260714_121051.CATPart`. Its PartBody contains
      `Rim_Barrel`, `Lofted_Spoke`, `Lofted_Spoke_Pattern`, `Wheel_Hub`, and
      `Center_Bore_And_Lugs`; CATIA reported 3,145,029.9 mm3 and 8.49 kg. Isometric,
      side, and front views visually confirmed the axial crown, ten evenly patterned
      tapered spokes, hub/rim intersections, bore, and five lug holes. The
      `Spoke_Construction` geometrical set was initially visible. It is now put in
      No Show mode after the final update (live-verified 2026-07-19), so construction
      geometry does not obstruct the default wheel view.
    - **Valve hole is implemented and verified live against `.42` (2026-07-14).**
      The wheel validator places one radial drilling on the flat drop-center wall,
      maintains 2 mm axial clearance from the profile transitions and the nearest
      +X spoke, and rejects combinations where the requested diameter cannot fit.
      A sketch on a radial offset plane is cut through the 8 mm wall by a symmetric
      `Pocket`; the legacy call shape still uses the 11.3 mm default. A full live
      build completed as `MCP_Wheel_Valve_Hole_20260714_123338.CATPart`, with
      `Valve_Hole` last in the PartBody and no CATIA update errors. Its volume was
      3,144,227.5 mm3, about 802.4 mm3 below the pre-hole build, matching the
      expected cylinder volume for diameter 11.3 x 8 mm. A right-view capture showed
      the barrel and drop-center, although visible `Spoke_Construction` geometry
      prevents treating that screenshot alone as a clean visual inspection of the
      circular edge; the feature tree, successful update, and volume delta are the
      acceptance evidence for this stage.
    - **Fillet/draft styling — partially applied (see item 14 for the full story).**
      Constant spoke-root fillets are now wired into `catia_design_wheel` and land
      live (10/10 on a test build), pending visual QA of edge targeting. Casting
      draft is still not applied in the composite (the `catia_advanced_draft` solver
      semantics are unresolved). Both base `catia_fillet` and `catia_draft` were found
      to be non-functional and were fixed (fillet) / diagnosed (draft) this session.
    - **No text/engraving capability exists anywhere in the tool set.** A branded
      wheel (raised or engraved logo/model text on a spoke) cannot be produced —
      this would be new capability (sketch text + emboss/pocket), not a wiring gap.
    - **Not in scope regardless of the above**: GD&T, Class-A surface continuity
      (G2/G3), FEA/fatigue/impact certification, DFM sign-off — see the Goal
      section's stated ceiling. Closing the gaps above gets to "matches this
      drawing's geometry," not to a released, certified part.
    - `catia_loft`, `catia_fill`, `catia_join`, and the wheel's PartBody-activated
      `CloseSurface` path are now verified against live CATIA. `catia_sew_surface`,
      `catia_variable_fillet`, and `catia_advanced_draft` remain unverified and must
      still be smoke-tested before they are chained into the wheel composite.

13. **Deployment host moved 192.168.5.10 → 192.168.5.42** (2026-07-13). See
    [`DEPLOYMENT.md`](DEPLOYMENT.md) — updated throughout, plus a new
    "Checking connectivity" section with a TCP-reachability and an authenticated
    MCP `initialize` check. Re-run the Open Work #1 smoke-test sequence against the
    new address before assuming prior live-verification results (items 1-11 above)
    still hold on this host — they were confirmed against `.10`; nothing suggests
    the CATIA install itself changed. Authenticated MCP `initialize` was re-confirmed
    on 2026-07-14 (`catia-v5-mcp` 1.28.1, 95 published tools). The new `wheel.py` and
    `sketcher.py` were then deployed through the SMB admin share with matching
    SHA-256 hashes; the previous files are in backup `wheel-profile-20260714-104436`.
    Follow-up hotfix deployments on the same date added the `FirstAngle` setter fix
    (`shaft-angle-20260714-105002`), ActiveViewer fallback for view/screenshot tools
    (`viewer-fallback-20260714-105705`), the missing `paths.py`
    (`missing-paths-20260714-111717`), and an output-path guard for repeated wheel
    saves (`output-path-guard-20260714-113021`). The spoke-loft work was deployed
    through `spoke-loft-20260714-114004`, `spoke-order-hotfix-20260714-114926`, and
    the final spline/capped-skin implementation
    `spoke-spline-skin-20260714-120806`; each deployment had matching local/remote
    SHA-256 hashes. The
    previously pending `.42` geometry smoke tests are now complete: `Shaft`,
    `catia_design_wheel`, `catia_fit_all`, `catia_set_view`, and `catia_screenshot`
    all executed live. The remaining screenshot caveat is format fidelity, not tool
    reachability: CATIA currently emits EMF payloads under `.png` filenames.

14. **Styling phase (casting draft + spoke-root fillets) — started 2026-07-14.
    Selection subsystem fixed and live-verified; two tool method-signature bugs
    diagnosed and fixed locally, pending a second deploy.** This is the next fidelity
    item after barrel/loft/valve (item 12). A live smoke test on `.42` of the two styling
    primitives the wheel needs surfaced three real bugs (the scratch pads built fine;
    these are selection/method failures, not geometry). In dependency order:
    - **[FIXED + LIVE-VERIFIED] Topological reference selection was completely broken.**
      `catia_advanced_draft` and `catia_list_subelements` failed at
      `CreateReferenceFromObject` with `E_INVALIDARG` (`0x80070057`). Root cause:
      `GeometryContext.list_subelements` built each edge/face Reference with
      `part.CreateReferenceFromObject(item)` on the raw topological `Value` of a
      `Selection.Search("Topology.*,sel")` result — rejected on this install. This one
      call underpins **all** index/`nearest_point`/`normal` sub-element selection, so it
      took down variable fillet, advanced draft, and the item-5 geometric-query selection
      together. (Contrast with the base `catia_fillet`/`catia_draft`, which operate on
      `_get_last_shape()` — the whole feature — with propagation and never build a
      topological Reference, which is why they always worked live and these didn't.)
      **Fix:** read the reference from the search result's `SelectedElement.Reference`
      property instead of rebuilding it (old call kept as fallback). Deployed to `.42`
      and re-tested 2026-07-14: `catia_list_subelements` now returns proper BRep
      references for all 12 edges / 6 faces of a test pad. This also unblocks item 5.
    - **[METHOD FIXED + DEPLOYED; solver input still to tune] `catia_variable_fillet`.**
      Was `AddNewSolidEdgeFilletWithVariableRadius(edge, 1, radius)`; the real CATIA
      member is `AddNewSolidEdgeFilletWith**Varying**Radius(edge, propagMode,
      variationMode, radius)` (4 args), and per-vertex radii use `AddImposedVertex`, not
      `AddRadiusVariationAtVertex` (confirmed against pycatia's `ShapeFactory`/
      `VarRadEdgeFillet` source). Fixed (propag=1 tangency, variation=1 cubic) and
      deployed. Live re-test 2026-07-14: the method now **resolves and creates** the
      feature, but `UpdateObject` then fails with `E_FAIL` (`0x80004005`) — a varying
      fillet with only a default radius and **no imposed vertices** is under-defined.
      Next experiment: supply `variations` with `AddImposedVertex` radii at the edge's
      end vertices (selection now works, so vertex refs are obtainable), or fall back to
      `catia_fillet`'s constant-radius path for the wheel.
    - **[METHOD FIXED + DEPLOYED; solver input still to tune] `catia_advanced_draft`.**
      Was a nonexistent 6-arg overload (`Member not found`, `-2147352573`) that also
      passed the pull direction as a Reference. Real signature is 10 args:
      `AddNewDraft(face, neutral, neutralMode, parting, dirX, dirY, dirZ, mode, angle,
      multiselMode)` with the pull direction a **vector** (three doubles). Reworked the
      tool: `pull_direction` takes `"xy"/"yz"/"zx"` or `{x,y,z}`, added a required
      `neutral` reference (parting defaults to it) and optional `propagation`
      (none/smooth); enums standard=0/reflect=1, neutral none=0/smooth=1,
      multiselection=0. Deployed. Live re-test 2026-07-14: the 10-arg call now
      **resolves**, but fails inside `AddNewDraft` with `E_FAIL` — the neutral was the
      origin `xy` plane; `AddNewDraft` wants a real **planar face of the body** as the
      neutral, and the drafted face must be adjacent to it. Next experiment: select a
      real planar face (e.g. the pad's bottom) as `neutral` and an adjacent side face to
      draft; also confirm `_choose_subelement`'s `normal`-based pick returns the intended
      side face (item 5 is now testable end-to-end).
    - **[MAJOR CORRECTION] The base `catia_fillet` and `catia_draft` are ALSO broken —
      they were never actually verified to produce a feature; the earlier "verified live"
      status only meant the `part.ShapeFactory` AttributeError was gone (item 2), not that
      a fillet/draft ever computed.** Confirmed live 2026-07-14:
      - `catia_fillet` passed `_get_last_shape()` (the whole Pad feature) to
        `AddNewSolidEdgeFilletWithConstantRadius`, which needs an **edge Reference**
        (`TriDimFeatEdge`) → `E_FAIL`. **Fixed (local, pending deploy):** `catia_fillet`
        now takes an `edge` reference spec and resolves it through `GeometryContext`
        (the selection fix makes this possible); the whole-feature path is removed with a
        clear error. This constant-radius edge fillet is the primitive the wheel's
        spoke-root blends actually need.
      - `catia_draft` called a 3-arg `AddNewDraft(shape, neutral, angle)` overload that
        does not exist here → `DISP_E_BADPARAMCOUNT` ("Invalid number of parameters").
        The only real overload is the 10-arg one now used by `catia_advanced_draft`.
        `catia_draft` should either be pointed at that call or deprecated in favour of
        `catia_advanced_draft`.
      - So there is **no already-working styling fallback** — every fillet/draft path
        needs valid references (now obtainable) and, for varying-fillet/draft, valid
        solver inputs. Constant-radius edge fillet is the closest to done.
    - **[FIXED + LIVE-VERIFIED] `catia_fillet` edge fillet now works.** Reworked to resolve
      an `edge` spec through `GeometryContext`. The first deploy exposed a deeper wall:
      `AddNewSolidEdgeFilletWithConstantRadius` accepted the edge ref and created the
      feature, but `UpdateObject` failed with `E_FAIL` — consistently, across constant and
      varying fillets and both index- and nearest_point-based selection. **Root cause:**
      `resolve()` stored the working `SelectedElement.Reference` but never used it — for a
      chosen sub-element it rebuilt the reference via `CreateReferenceFromName(DisplayName)`,
      and that rebuilt reference is accepted by `AddNew*` but is **not solver-valid** (fails
      at update). **Fix:** `resolve()` now returns the captured `SelectedElement.Reference`
      object directly (name/object rebuild kept only as fallback). Re-tested live: constant
      edge fillet solves by both index and nearest_point (`EdgeFillet.1`/`.2`), and a
      varying fillet with no imposed vertices solves too. This is the completion of the
      selection fix and unblocks all edge-based styling.
    - **[FIXED + LIVE-VERIFIED 2026-07-19] varying-fillet and advanced-draft solver
      semantics.** `catia_variable_fillet` now accepts variation `position` values from
      0 to 1 and creates real `PointOnCurve` controls before
      the fillet. Passing an adjacent topological box vertex to `AddImposedVertex` still
      `E_FAIL`s even when its BRep neighbours prove that it belongs to the selected edge;
      a HybridShape point genuinely on the edge is the solver-valid input on this seat.
      Live smoke: one Pad edge with controls at 25%/75%, radii 2/5 mm, updated as
      `Item14_VariableFillet_Smoke`. For `catia_advanced_draft`, omitting `parting` now
      supplies an empty CATIA Reference instead of incorrectly substituting the neutral
      face; the domain pull direction is set explicitly and additional `faces` are added
      through `DraftDomain.AddFaceToDraft`. Live smoke: an adjacent Pad side face drafted
      5 degrees about a planar Pad limit face along +Z, updated as
      `Item14_AdvancedDraft_Smoke`. Both tests are reproducible with
      `python scripts/smoke_item14.py`; scratch documents are closed without saving.
    - **[WIRED INTO THE WHEEL + LIVE-VERIFIED] constant spoke-root fillet phase.**
      `catia_design_wheel` now runs a best-effort, **non-fatal** `_apply_spoke_fillets`
      phase after the hub: for each spoke it selects a junction edge by `nearest_point` at
      `(hub_radius·cosθ, hub_radius·sinθ, 0)` (trying the `Wheel_Hub` then
      `Lofted_Spoke_Pattern` feature) and applies a constant fillet at
      `min(fillet_radius, rim_thickness/2, spoke_thickness·0.4)` with tangency
      propagation. Gated by a new `apply_spoke_fillets` arg (default true); a failure is
      recorded as a warning and never discards the solid. Live build 2026-07-14
      (400 mm / 5×114.3 / 10-spoke) returned `"status":"complete"` with
      **`spoke_fillets: 10/10 at R4 mm`** and saved `MCP_Wheel_SpokeFillet_20260714.CATPart`.
      **Caveat — needs visual QA:** the build's volume dropped ~13% vs. the prior no-fillet
      lofted build (2.74 M vs 3.14 M mm³). A concave root fillet *adds* material, so the
      decrease means the `nearest_point` pick is landing at least some fillets on **convex**
      spoke edges (material removal), and/or tangency propagation is rounding long runs.
      The phase mechanics are proven; the edge *targeting* likely needs refinement (a
      point biased to the concave weld, or a smaller radius). Visual confirmation is
      currently blocked by the EMF-screenshot bug (item 13 / DEPLOYMENT.md) — fixing that
      is now on the critical path for closing this out.
    - **[FIXED + LIVE-VERIFIED] `catia_screenshot` EMF-vs-PNG bug.** `_screenshot` hardcoded
      `CaptureToFile(1, ...)` and `1` is `catCaptureFormatEMF`, so it always wrote EMF
      regardless of extension. CATIA's `CatCaptureFormat` has **no PNG** (only
      CGM=0/EMF=1/TIFF=2/BMP=4/JPEG=5). Fixed (`export.py`): choose the format from the
      file extension; for a `.png` (or unsupported) path, write **JPEG** and rewrite the
      returned path to `.jpg` so content and name agree. Deployed and verified live: iso/
      front/right captures of the filleted wheel wrote real JPEGs, copied back and viewed.
      **QA result:** the wheel is structurally sound and undamaged — correct barrel
      profile (flanges/bead-seats/drop-center), ten crowned spokes, hub, bore, lugs.
      **The fillet placement is correct** (confirmed by a same-spec A/B, not just the
      screenshots): baseline `apply_spoke_fillets:false` = 2,740,178 mm³ vs filleted
      2,742,278 mm³, i.e. the fillets *add* ~2,100 mm³ — the signature of **concave
      spoke-root fillets** filling the corner, exactly as intended. The earlier "~13%
      volume drop" was a false alarm from comparing against a different-spec prior build;
      the correct same-spec comparison resolves it. `nearest_point` targeting lands on the
      right (concave root) edges.
    - **[FIXED + LIVE-VERIFIED] `catia_open_document` already-open modal.** Opening a
      document that is already open raised a modal that hung the call until dismissed
      (observed 2026-07-14 opening the just-saved wheel, still open as `Part26`; five
      queued calls timed out before it cleared). `document.py`'s `_open_document` now scans
      open documents by normalized `FullName` and, on a match, activates and reuses the
      existing document instead of calling `Documents.Open` again. Verified live: reopening
      the already-open wheel returned "already open; reused" in ~2 s (was 120 s+ hang).
    - **Historical next-step note (resolved below):** the styling phase's primitives are delivered and live-verified. Remaining,
      in rough order: (1) cosmetic — hide the `Spoke_Construction` geometrical set by
      default; (2) optional
      zoomed-junction capture / a camera-zoom tool for close-up QA (the A/B volume check
      already confirmed the fillets are correct concave root blends).
    - **[FIXED + LIVE-VERIFIED] Wheel construction visibility.**
      `catia_design_wheel` now puts `Spoke_Construction` into No Show after all dependent
      Part Design work completes and before saving. Live smoke on `.42` passed on
      2026-07-19 with `python scripts/smoke_wheel_visibility.py`: the built wheel reported
      a complete `construction_visibility` phase for `Spoke_Construction`, then its
      temporary CATPart closed without saving.
    - **[FIXED + LIVE-VERIFIED] Close-up camera zoom for QA.** `catia_zoom_view`
      adds deterministic CATIA viewer zoom with an `in`/`out` direction and 1-20 steps.
      Use it after `catia_set_view` and `catia_fit_all`, then call `catia_screenshot` for
      a reproducible close-up. Live smoke on `.42` passed on 2026-07-19 with
      `python scripts/smoke_zoom_view.py`: a temporary Pad was fit in front view,
      zoomed in three steps and captured as a valid 168,330-byte JPEG (FFD8 signature),
      then the temporary CATPart closed without saving.
    - **Deployed to `.42` this session (all with `.bak` backups + verified SHA-256):**
      `_geometry.py` (selection fix + reference-object fix — verified working),
      `part_design_advanced.py` (varying-fillet + advanced-draft signatures),
      `part_design.py` (fillet edge-ref — verified working). None committed to git yet.
    - **Deployed to `.42` on 2026-07-19:** the final `part_design_advanced.py` was
      synchronized directly and matched local SHA-256
      `ABA4F59F6DB53213CD6B4EEE5D24E35758B913816DAFBE7B18C8259586144F01`.
      MCP restarted as PID 35748 in interactive session 8; authenticated initialize
      returned HTTP 200 before the final two-tool smoke passed.

15. **Drawing (CATDrawing) tools — implemented and live-verified 2026-07-15.** New
    `catia_mcp/tools/drawing.py` (`DrawingTools`, registered in `server.py`; published tool
    count 95 → 103 at the time) generates associative 2D drawings from an open 3D part. Eight tools,
    all exercised live against `.42` on the lofted wheel: `catia_new_drawing` (sheet
    paper/orientation/scale), `catia_drawing_base_view` (front/back/top/bottom/left/right/
    iso), `catia_drawing_projection_view`, `catia_drawing_section_view`,
    `catia_drawing_detail_view`, `catia_drawing_update`, `catia_drawing_info`, and the
    one-call `catia_drawing_from_part` (front+right+top+iso + optional PDF). PDF export
    reuses `catia_export` (`ExportData(path,"pdf")`; `pdf` added to its schema enum). A
    full six-view sheet (front/top/right/iso + section + detail) plus a one-call
    `from_part` drawing were built, screenshotted (JPEG), and PDF-exported; the section
    view shows the real barrel/hub cross-section and the detail view a magnified region.
    Scope excluded (deferred): dimensions and DXF.

    A ninth tool, `catia_fill_drawing_bom` (fills an existing drawing's BOM/specification
    table, matching rows by component name), was added later in the bundled `9be2035`
    commit described in the scope note at the top of this file. It's genuinely GSD/drawing
    scope, unlike the rest of that commit. It was live-verified on `.42` on 2026-07-21
    with `python scripts/smoke_drawing_bom.py`: the smoke created a three-row
    DrawingTable in a temporary A4 drawing, then found that same table and updated both
    quantities without creating a second table. The temporary CATDrawing was closed
    without saving.

    A tenth tool, `catia_drawing_add_text`, adds a named text annotation to a chosen
    drawing view at explicit view-relative millimetre coordinates. It was live-verified
    on `.42` on 2026-07-21 with `python scripts/smoke_drawing_text.py`: the smoke
    created `SmokeNote` in `Background View` at `(35, 25)`, then confirmed it through
    `catia_drawing_info`; the temporary CATDrawing was closed without saving.

    Method/behaviour drift found and fixed live (same class as the 3D gotchas):
    - **3D link is `GenerativeBehavior.Document = part_doc`, not `GenerativeLinks.AddLink`.**
      `AddLink(document)` fails with `E_FAIL` on this seat; setting the `Document` property
      is the working association. Base views were empty until this switch.
    - **Derived views (projection/section/detail) do not inherit the parent's 3D source** —
      they define the relationship but generate **no geometry** until the parent's document
      link is carried onto them (`_carry_link`: `child.GB.Document = parent.GB.Document`,
      `CopyLinksTo` fallback). Projection/top/right views came out empty frames until this.
    - **The API does not auto-position or auto-scale derived views** (they land at `0,0` /
      `1:1`, off-sheet). Projection/section/detail now set `view.Scale` (inherited from the
      parent) and `view.x/y` (projection: offset by `gap` in the projection direction).
    - `Documents.Add("Drawing")` works; `CatPaperSize` A0–A4 = 2–6, orientation 0/1,
      `CatProjViewType` right/left/top/bottom = 0/1/2/3 confirmed. The section-profile
      SAFEARRAY was accepted as a plain Python tuple (VARIANT fallback path unused so far).
      `DefineSectionView`/`DefineCircularDetailView` auto-name the views (e.g. `SecAA-A`,
      `DetBB`).
    - Left for a later pass: dimensions/DXF; smarter auto-layout (offsets are fixed
      `gap` mm, not part-size aware — no bounding box available, see item 11); hiding the
      section/detail callout dressing if undesired.

16. **Second spoke style: `y_fork` (mesh/Y-spoke) — implemented and live-verified
    2026-07-16.** Closes item 7's "expand the spoke_style family" open work. Each spoke
    now forks into two thinner branches partway to the rim (BBS-mesh look), requested by
    the user against a reference image. Reuses every primitive `wheel.py` already proved
    for `simple_lofted` — no new CATIA capability — just applies the section→spline→
    loft→2 caps→join→`AddNewCloseSurface` pipeline (now extracted into
    `_build_spoke_solid`) three times per spoke unit instead of once: one trunk (hub →
    fork point) and two branches (fork point → their own point on the rim, offset
    tangentially via a new `"lateral"` field on each section, plumbed through
    `_spoke_section_points`/`_spoke_guide_points`). The branch-root cross-section is
    sized/offset to sit nested inside the trunk's fork-end cross-section so the three
    lofted solids overlap in 3D — Part Design's implicit add then fuses them into one Y
    lump automatically, the same overlap trick the file already used to fuse the spoke
    onto the hub/rim. Each of the three solids is then circularly patterned separately
    (three `AddNewCircPattern` calls, identical center/axis/count/angle) since a Part
    Design pattern only replicates the one feature it's given. New `validate()` inputs:
    `fork_fraction` (0.2–0.7, default 0.42, where along hub→rim the fork happens) and
    optional `fork_spread` (auto-computed from rim circumference/spoke_count when
    omitted, with a clearance check against neighboring spokes' branch tips — same style
    of self-intersection guard as the existing `spoke_thickness`/`spoke_count` check).
    `_apply_spoke_fillets`'s candidate feature list generalized to try every pattern
    feature actually built, not a hardcoded name.

    **Live-verified first try, no fix cycle needed** (unusual for this file's history —
    see items 3/8/9/14 for the fillet/loft/order bugs earlier styles needed): deployed
    `wheel.py` to `.42` over SMB, restarted the remote server, then called
    `catia_design_wheel` with `spoke_style="y_fork"`, `spoke_count=10`, the same
    457.2/203.2/114.3/67.1 mm dimensions used throughout this doc. All 7 phases reported
    `complete` (document, parameters, rim, hub_and_spokes, spoke_fillets 10/10 at R4mm,
    mounting_features, valve_hole); saved `MCP_Wheel_YFork_20260716_173101.CATPart` +
    `.stp`, volume 3,183,715 mm3 / 8.60 kg. ISO and front screenshots confirm the Y-fork
    mesh pattern visually matches the reference image: ten trunks fork cleanly into two
    branches each, forming the triangular rim-side windows.

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
