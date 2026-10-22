# CATIA 3DEXPERIENCE (V6) support

The server drives CATIA V5 and CATIA on the 3DEXPERIENCE platform with the
same tools. This page describes what changes on 3DEXPERIENCE, what does not
port and why, and how to validate it on your installation.

## Status

The 3DEXPERIENCE code paths were written against the published
3DEXPERIENCE automation object model and field-reported macros (sources
below), and are covered by offline contract tests with COM doubles
(`tests/test_3dexperience.py`).

**Live validation: one release so far.** `scripts/live_smoke_test.py
--drawing --plm-type 3DShape` passes on 3DEXPERIENCE R428 SP6 (B428_Cloud):
51 passed, 2 expected skips (STEP export, front view of a standalone 3D
Shape), 0 failed. A front view of a Physical Product and a right projection
view of it were also created through the tools on that release. Section,
detail and isometric views are bound from the documented signatures but not
yet run live. Treat other releases as unvalidated until the smoke test
passes there, and report what fails.

CATIA V5 behavior is unchanged, with one fix: component positions are now
read correctly (see the changelog).

## Setup

1. Start the native CATIA app from the 3DEXPERIENCE launcher, log in, and
   pick the collaborative space you want new content to go to.
2. Start the MCP server as usual (`python -m catia_mcp` or `catia-mcp`).
3. Call `catia_connect`. It attaches to `CATIA.Application`, which
   3DEXPERIENCE registers like V5, and reports the detected platform.

The platform is detected from the object model (session services and
editors exist only on 3DEXPERIENCE). Force it with `--platform 3dx` or the
`CATIA_MCP_PLATFORM=3dx` environment variable if detection is wrong. With
both V5 and 3DEXPERIENCE installed, `CATIA.Application` points to whichever
registered last; run only the one you want.

## How the server finds things

| Need | 3DEXPERIENCE route |
|------|--------------------|
| Active Part | `ActiveEditor.ActiveObject` when it is the Part (3D Shape level); otherwise the root occurrence → `ReferenceRootOccurrenceOf` → `RepInstances` → `ReferenceInstanceOf` → `GetItem("Part")` (3D Part level) |
| Selection | `ActiveEditor.Selection` (searches only work in the active editor) |
| Topology (`Face.N`, `Edge.N`, `Vertex.N`) | `Topology.<Kind>` search from the **body**, never from its last shape: on R428 a last-shape search returns only the cells that feature created (2 faces when the last feature is a Hole) or none (a boolean, `Add.1`), while the body search returns the final solid (14 faces for a block with 4 holes). V5 keeps its field-validated search from the last shape, falling back to the body when that finds nothing. |
| Product structure | `Editor.GetService("PLMProductService").RootOccurrence` (or `PLMProductContext`), then `Occurrences` / `InstanceOccurrenceOf` / `ReferenceInstanceOf` |
| PLM attributes | `GetAttributeValue` / `SetAttributeValue` on the VPMReference (3D Part, product) or VPMRepReference (3D Shape, drawing; the Part's `Parent`) |
| Create | `GetSessionService("PLMNewService").PLMCreate` |
| Open | `GetSessionService("Search").DatabaseSearch` + `GetSessionService("PLMOpenService").PLMOpen` |
| Save | `GetSessionService("PLMPropagateService").PLMPropagate` |
| Measure | `Editor.GetService("MeasurableService")`, `Editor.GetService("InertiaService")` |

`PLMCreate`, `PLMOpen` and every out-parameter (points, arrays) go through
`SystemService.Evaluate` running a small VBScript, the same detour the V5
code uses for arrays, because out-parameters do not marshal through
late-bound COM.

## Tool behavior on 3DEXPERIENCE

| Area | Behavior |
|------|----------|
| Sketcher, Part Design, GSD, Knowledgeware | Same factory APIs as V5 once the Part is resolved. |
| `catia_new_part` | Tries a 3D Part, falls back to a 3D Shape when refused (`plm_type` forces one). Title goes to `V_Name`. In session only until saved. |
| `catia_new_product` | Physical Product (`VPMReference`); refused without the matching licence/role. |
| `catia_save_document` | Saves the **active editor's** content to the database. No Save As. |
| `catia_close_document` | Closes the active window; unsaved changes are discarded unless `save=true`. |
| `catia_open_document` | Works only where the installation still exposes `Documents.Open`; otherwise use `catia_open_from_database`. |
| `catia_search_database`, `catia_open_from_database` | Search by title (`V_Name`) or another attribute, `*` wildcards. Opening refuses to guess between several matches: pass `revision` or `index`. |
| `catia_get_plm_attributes`, `catia_set_plm_attributes` | Attributes of the object in the active editor. Writes stay in session until saved; your role and data model decide what is writable. |
| `catia_hole` | `AddNewHoleFromSketch` ignores its depth argument on R428 (the bottom limit stays 10 mm), so the server sets `BottomLimit.Dimension.Value` and reads it back (on V5 too; a depth that does not take fails with `WRONG_GEOMETRY_EFFECT`). The body volume is measured before and after. A hole that removes nothing (live: sketched on the XY plane at the pad's bottom face, it drilled into air) is reversed once with `Hole.Reverse()` and measured again; if it still removes nothing the call fails with `FEATURE_NO_EFFECT`, leaving the hole in the tree. The result reports the removed volume. |
| `catia_user_pattern` | A Hole seed is refused with `UNSUPPORTED_CAPABILITY` before anything is created. On R428 CATIA rejects a user pattern of a sketch-positioned Hole on update. The missing input is probably the anchor point, but `DSYAutomation.chm` R428 types `UserPattern.AnchorPoint` only as `CATIABase`, with no `SetAnchorPoint` and no example, so no deterministic anchor is established. Cut circles with `catia_pocket` instead, or create one hole per position. Other seeds use the V5 recipe. |
| `catia_circ_pattern` | The V5 donor-document recipe needs files; on 3DEXPERIENCE the rotation axis is a GSD line kept in a `MCP_Construction` geometrical set of the part. |
| Measurement | Through `MeasurableService` / `InertiaService`. The `CATMeasurableType` codes are read from the installation's type library and picked by name (`GetMeasurable` returns whatever type is asked for). Minimum distance is `MeasurableBetween.DistanceMinTo`, which also returns the closest points. See units below. |
| `catia_list_components`, `catia_move_component`, `catia_get_product_tree` | Occurrences and instance positions. |
| `catia_insert_existing_component`, `catia_add_new_part` | The automation API lost its add/remove structure methods after 2013x, so the server opens (or creates) the component in its own editor, copies its root, pastes it under the active product's root, and checks that exactly one child was added. Nothing is rolled back if the check fails. |
| Putting an existing 3D Shape into a 3D Part / product | No tool. Live on R428 SP6: pasting the shape under the product root is refused, and `VPMRepInstances.Add` exists in the type library but is undocumented and refused. The shape's **geometry** can be copied into the 3D Part's own shape: copy its body, then `Selection.PasteSpecial "CATPrtResultWithOutLink"` on the target Part. `"CATPrtResult"` (as result with link) does not create a link between two shapes from a script; `DSYAutomation.chm` says such links "must be done interactively", and a live propagation test confirmed the pasted solid did not follow its source. |
| Assembly constraints | Not available: 3DEXPERIENCE uses engineering connections, which the documented automation API does not create. `catia_list_constraints` lists engineering connections. |
| `catia_export` | `UNSUPPORTED_CAPABILITY`: `DSYAutomation.chm` documents no file export for database content, and on R428 the compatibility document refuses `ExportData`. Use CATIA's Export command (STEP needs the ST1 licence). Screenshots work. On both platforms an export only succeeds once the file is verified on disk. |
| Drawings | `catia_new_drawing` creates a Drawing; texts, tables and dimensions keep the V5 API. Generative views use the `DrawingDefineGenView` factory, whose `Define*` functions take the anchor (`iXPos`, `iYpos`) first and `iViewStyle`, `iComputeUpdate`, `iViewProp` (from `GetSessionService("CATDrawingGenService").DrawingGenViewProp`) last. The server reads the signature from the type library and binds arguments **by parameter name**, refusing with the discovered signature before calling when a name is unknown. Front views project product instances: the server passes the product's root occurrence (also for a 3D Shape edited inside a product, which `part_name` can name by the product's title). A standalone 3D Shape is refused with `UNSUPPORTED_CAPABILITY`, because CATIA silently creates no view for it. Face-driven and single-body views are V5-only. Generated (projected) edges are not exposed to automation (live R428: a selection search returns them as the view itself, without a reference), so associative dimensions come only from `catia_drawing_generate_dimensions`. On R428 that generated sketch constraints **and** Pad/Pocket lengths (live: hole depth 20 and block height 40 in a section view, the hole's radius constraint as R4 in the front view). The API has no diameter constraint type, and `DrawingDimension.DimType` is read-only, so a hole shows as R, not Ø. A pasted solid without history generates nothing. |

### Drafting behaviors observed on R428

Live on R428 SP6. No tool depends on them today; code that adds such
features must account for them.

- `DrawingRoot.Standard = "ASME"` is silently ignored: the standard stays
  `"ISO"` and no error is raised. Read the property back after setting it.
- `DrawingGDT` reference cells written with `GetTextRange(1, i).Text = ref`
  commit only when a range is read back afterwards; otherwise the last
  written cell is lost. Read each range back after writing it.
- Section view labels are composed as prefix + ident + `"-"` + ident +
  suffix, so `SetViewName("SECTION ", "A", "")` gives `SECTION A-A`.
  `catia_drawing_section_view` does not call `SetViewName`; its `name`
  sets `view.Name`, which `DSYAutomation.chm` describes as the label
  prefix.

## Saving and safety

Saving writes to the shared 3DSpace database, visible to colleagues
according to your collaborative space. No tool saves implicitly: new parts,
attribute changes and edits stay in the session until `catia_save_document`
(or `catia_close_document` with `save=true`). `scripts/live_smoke_test.py`
saves nothing unless run with `--save`.

`catia_run_script` runs arbitrary VBScript inside CATIA with your rights,
so it is off unless the server starts with `--allow-scripts`.

## Licences and roles

Field reports agree that scripted creation of a 3D Part (`"3DPart"`) or a
Physical Product (`"VPMReference"`) requires an extra licence (reported as
E70 or VMX) and otherwise fails with "Operation not authorized"; 3D Shapes
and Drawings can always be created. STEP export requires the ST1 exchange
licence. `catia_diagnose` reports which services your session exposes.

## Measurement units

V5 automation returns volume and area in MKS (m³, m²) and point coordinates
in mm; the server converts everything to mm-based units. On 3DEXPERIENCE
R428 SP6 the smoke test confirmed the same convention for volume, area and
coordinates (a 100 × 60 × 40 mm block measures 240000 mm³, its 100 × 60
face 6000 mm², its bounding box 100/60/40), and `DistanceMinTo` returns mm
(50 mm and 10 mm on known construction geometry). Results carry a
`units_note`. On another release, the smoke test settles it: a ratio of 1e9
or 1e-9 in the report means the convention differs.

## Discovering the API on your release

The full reference ships with the installation as `DSYAutomation.chm` in
`win_b64\code\bin`. The server reads the same API live:

```text
catia_inspect_api  path="part.ShapeFactory"  filter="AddNew"
catia_inspect_api  path="editor.GetService(\"MeasurableService\")"  enum="CATMeasurableType"
catia_inspect_api  path="app"  filter="Export"
```

Paths start at `app`, `editor`, `document`, `part`, `product`, `selection`
or `window`, and only read properties or call the getters `Item`,
`GetItem`, `GetService`, `GetSessionService`, `GetWorkbench`,
`GetTechnologicalObject` and the occurrence/instance navigation methods.

## Validating and reporting

On the Windows machine running CATIA:

```bat
python scripts\live_smoke_test.py --drawing --report smoke_report.json
```

Without the licence for scripted 3D Part creation, add `--plm-type 3DShape`:
the default first tries a 3D Part, and CATIA shows its refusal as a modal
"Operation not authorized" dialog that blocks the run until you close it.

It connects, runs `catia_diagnose`, builds and measures a throw-away part,
exercises sketches, pads, pockets, patterns, fillets, bodies, booleans,
topology after a boolean, GSD, distances on known geometry, parameters,
views, screenshots and API inspection, and writes a JSON report with every
tool's output. Send that report and the `catia_diagnose` output with your
3DEXPERIENCE release when something fails.

## Sources

- Rand 3D, "Transitioning Macros from CATIA V5 to 3DEXPERIENCE" series:
  creating/opening/saving, services, product modeler, part modeling and
  drafting.
- Eng-Tips threads on 3DEXPERIENCE `MeasurableService` and `InertiaService`
  macros.
- Scripting4V5 on V6 `PLMNewService` creation and naming.
- CATIA Widgets on navigating the V6 product structure.
