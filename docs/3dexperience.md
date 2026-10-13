# CATIA 3DEXPERIENCE (V6) support

The server drives CATIA V5 and CATIA on the 3DEXPERIENCE platform with the
same tools. This page describes what changes on 3DEXPERIENCE, what does not
port and why, and how to validate it on your installation.

## Status

The 3DEXPERIENCE code paths were written against the published
3DEXPERIENCE automation object model and field-reported macros (sources
below), and are covered by offline contract tests with COM doubles
(`tests/test_3dexperience.py`). **They have not yet been run against a live
3DEXPERIENCE session.** Treat results as unvalidated until
`scripts/live_smoke_test.py` passes on your release, and report what fails.

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
| Selection | `ActiveEditor.Selection` |
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
| `catia_circ_pattern` | The V5 donor-document recipe needs files; on 3DEXPERIENCE the rotation axis is a GSD line kept in a `MCP_Construction` geometrical set of the part. |
| Measurement | Through `MeasurableService` / `InertiaService`. The `CATMeasurableType` codes are read from the installation's type library. See units below. |
| `catia_list_components`, `catia_move_component`, `catia_get_product_tree` | Occurrences and instance positions. |
| `catia_insert_existing_component`, `catia_add_new_part` | The automation API lost its add/remove structure methods after 2013x, so the server opens (or creates) the component in its own editor, copies its root, pastes it under the active product's root, and checks that exactly one child was added. Nothing is rolled back if the check fails. |
| Assembly constraints | Not available: 3DEXPERIENCE uses engineering connections, which the documented automation API does not create. `catia_list_constraints` lists engineering connections. |
| `catia_export` | Not available unless the installation still exposes a document with `ExportData`. Use CATIA's Export command (STEP needs the ST1 licence). Screenshots work. |
| Drawings | `catia_new_drawing` creates a Drawing; texts, tables and dimensions keep the V5 API. Generative views use the `DrawingDefineGenView` factory: since its signatures are not public, the server reads them from the type library and binds arguments by kind and order, refusing with the discovered signature when the binding is not exact. Face-driven and single-body views are V5-only. |

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
in mm; the server converts everything to mm-based units. 3DEXPERIENCE
point coordinates are field-reported in mm. Volume and area are assumed to
follow the V5 MKS convention, and results carry a `units_note` saying so.
The smoke test settles it: it builds a 100 × 60 × 40 mm block and requires
240000 mm³ (a ratio of 1e9 or 1e-9 in the report means the convention
differs).

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

It connects, runs `catia_diagnose`, builds and measures a throw-away part,
exercises sketches, pads, pockets, patterns, fillets, bodies, booleans,
GSD, parameters, views, screenshots and API inspection, and writes a JSON
report with every tool's output. Send that report and the `catia_diagnose`
output with your 3DEXPERIENCE release when something fails.

## Sources

- Rand 3D, "Transitioning Macros from CATIA V5 to 3DEXPERIENCE" series:
  creating/opening/saving, services, product modeler, part modeling and
  drafting.
- Eng-Tips threads on 3DEXPERIENCE `MeasurableService` and `InertiaService`
  macros.
- Scripting4V5 on V6 `PLMNewService` creation and naming.
- CATIA Widgets on navigating the V6 product structure.
