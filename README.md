# CATIA V5 MCP Server

> Connect Claude AI to Dassault Systemes CATIA V5 via the Model Context Protocol (MCP).

[![Clones](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/daiemon12/catia-v5-mcp-server/main/traffic/badge-clones.json)](traffic/clones.json)
[![Views](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/daiemon12/catia-v5-mcp-server/main/traffic/badge-views.json)](traffic/views.json)

The first open-source MCP server for CATIA V5. Drive CATIA V5 CAD modeling from Claude Desktop or Claude Code using natural language.

![Repository traffic](traffic/chart.png)

## What it does

This MCP server exposes **50+ tools** that let Claude:

- **Create and manage documents** — new Part, Product (assembly), open, save, close
- **2D Sketching** — lines, rectangles, circles, arcs, splines, points, constraints
- **Part Design** — Pad, Pocket, Shaft, Groove, Fillet, Chamfer, Hole, Shell, Draft, Thickness, Patterns (rectangular/circular), Mirror
- **Assembly** — add components, Fix/Coincidence/Offset/Angle constraints, move/rotate
- **Measurement** — distance, inertia, bounding box, parameters
- **Export** — STEP, IGES, STL, 3DXML, VRML, screenshots
- **View control** — set standard views, fit all, capture screenshots

## Requirements

- **Windows** (COM automation is Windows-only)
- **CATIA V5** installed and licensed (R2016+)
- **Python 3.10+**
- **Claude Desktop** or **Claude Code**

## Quick Install (Recommended)

```bash
git clone https://github.com/daiemon12/catia-v5-mcp-server.git
cd catia-v5-mcp-server
bash setup.sh
```

The script handles everything: dependencies, Claude Desktop config, and verification.

## Manual Installation

### 1. Clone the repository

```bash
git clone https://github.com/daiemon12/catia-v5-mcp-server.git
cd catia-v5-mcp-server
```

### 2. Install dependencies

```bash
pip install -e .
```

Or manually:
```bash
pip install mcp pywin32
```

### 3. Configure Claude Desktop

Edit your Claude Desktop config file:
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

Add the server:

```json
{
  "mcpServers": {
    "catia-v5": {
      "command": "python",
      "args": ["-m", "catia_mcp"]
    }
  }
}
```

Or with an absolute path:

```json
{
  "mcpServers": {
    "catia-v5": {
      "command": "python",
      "args": ["C:/path/to/catia-v5-mcp-server/catia_mcp/server.py"]
    }
  }
}
```

### 4. For Claude Code

```bash
claude mcp add catia-v5 python -- -m catia_mcp
```

### 5. Start CATIA V5

Make sure CATIA V5 is running before asking Claude to interact with it. The server will automatically connect to the running instance.

If CATIA V5 is not running, the server will attempt to launch it (requires CATIA to be registered as COM server: `cnext.exe /regserver`).

## Usage Examples

Once configured, just talk to Claude:

### Create a simple part
> "Create a new CATIA part. Draw a 100x60mm rectangle centered at the origin on the XY plane, then extrude it 40mm."

### Design a bracket
> "Design a mounting bracket: start with a 120x80mm base plate, 5mm thick. Add 4 M6 mounting holes at the corners with 10mm edge distance. Then add two vertical ribs 30mm tall."

### Parametric modification
> "Show me all parameters of the active part. Then change the pad height to 60mm."

### Export for manufacturing
> "Export the current part to STEP format at C:/export/bracket.stp and take a screenshot of the isometric view."

### Assembly
> "Create a new assembly. Add the bracket from C:/parts/bracket.CATPart and the base from C:/parts/base.CATPart. Fix the base, then create a coincidence constraint between the two."

## Architecture

```
catia-v5-mcp-server/
├── catia_mcp/
│   ├── __init__.py
│   ├── __main__.py          # python -m catia_mcp entry point
│   ├── server.py            # MCP Server — tool registration & routing
│   ├── connection.py        # COM connection manager (win32com)
│   └── tools/
│       ├── __init__.py
│       ├── document.py      # Document management (9 tools)
│       ├── sketcher.py      # 2D Sketch tools (11 tools)
│       ├── part_design.py   # 3D Part Design features (15 tools)
│       ├── assembly.py      # Assembly/Product tools (9 tools)
│       ├── measurement.py   # Measurement & analysis (6 tools)
│       └── export.py        # Export & view control (4 tools)
├── pyproject.toml
├── requirements.txt
└── README.md
```

### How it works

```
Claude (Desktop/Code)
    │
    │ stdio (MCP JSON-RPC)
    ▼
catia_mcp/server.py (MCP Server)
    │
    │ Tool routing
    ▼
catia_mcp/tools/*.py (Tool modules)
    │
    │ win32com.client (COM Automation)
    ▼
CATIA V5 Application
```

1. Claude sends MCP tool calls over stdio
2. The server routes each call to the appropriate tool module
3. Each tool module uses `win32com.client` to drive CATIA V5 via COM
4. Results (JSON, text) are returned to Claude

## Tool Reference

### Document Tools (9)
| Tool | Description |
|------|-------------|
| `catia_connect` | Connect to CATIA V5 |
| `catia_disconnect` | Disconnect from CATIA V5 |
| `catia_new_part` | Create a new Part document |
| `catia_new_product` | Create a new Product (assembly) |
| `catia_open_document` | Open an existing document |
| `catia_save_document` | Save / Save As |
| `catia_close_document` | Close active document |
| `catia_list_documents` | List all open documents |
| `catia_get_active_document_info` | Get detailed info about active document |

### Sketcher Tools (11)
| Tool | Description |
|------|-------------|
| `catia_create_sketch` | Create sketch on XY/YZ/ZX plane |
| `catia_close_sketch` | Close sketch, return to Part Design |
| `catia_sketch_line` | Draw a line |
| `catia_sketch_rectangle` | Draw a rectangle (2 corners) |
| `catia_sketch_centered_rectangle` | Draw a centered rectangle |
| `catia_sketch_circle` | Draw a circle |
| `catia_sketch_arc` | Draw an arc |
| `catia_sketch_spline` | Draw a spline through points |
| `catia_sketch_point` | Create a point |
| `catia_sketch_constraint` | Add dimensional/geometric constraint |
| `catia_sketch_get_geometry` | List sketch geometry elements |

### Part Design Tools (15)
| Tool | Description |
|------|-------------|
| `catia_pad` | Pad (extrusion) |
| `catia_pocket` | Pocket (cut extrusion) |
| `catia_shaft` | Shaft (revolution) |
| `catia_groove` | Groove (revolution cut) |
| `catia_fillet` | Fillet (edge rounding) |
| `catia_chamfer` | Chamfer (edge bevel) |
| `catia_hole` | Hole (simple, counterbored, countersunk) |
| `catia_rect_pattern` | Rectangular pattern |
| `catia_circ_pattern` | Circular pattern |
| `catia_mirror` | Mirror about a plane |
| `catia_shell` | Shell (hollow out) |
| `catia_draft` | Draft angle |
| `catia_thickness` | Thickness offset |
| `catia_list_features` | List features in body |
| `catia_list_edges` | List edges for fillet/chamfer |

### Assembly Tools (9)
| Tool | Description |
|------|-------------|
| `catia_add_component` | Add existing part to assembly |
| `catia_add_new_part` | Create new part in assembly |
| `catia_fix_constraint` | Fix a component in place |
| `catia_coincidence_constraint` | Coincidence constraint |
| `catia_offset_constraint` | Offset constraint |
| `catia_angle_constraint` | Angle constraint |
| `catia_move_component` | Move/rotate a component |
| `catia_list_components` | List assembly components |
| `catia_list_constraints` | List assembly constraints |

### Measurement Tools (6)
| Tool | Description |
|------|-------------|
| `catia_measure_distance` | Measure distance between elements |
| `catia_get_inertia` | Volume, area, mass, center of gravity |
| `catia_get_bounding_box` | Bounding box dimensions |
| `catia_get_parameters` | List all parameters |
| `catia_set_parameter` | Modify a parameter value |
| `catia_update_part` | Force rebuild |

### Export Tools (4)
| Tool | Description |
|------|-------------|
| `catia_export` | Export to STEP/IGES/STL/3DXML/VRML |
| `catia_screenshot` | Capture 3D view to image |
| `catia_set_view` | Set view orientation |
| `catia_fit_all` | Fit all in view |

## Troubleshooting

### "pywin32 is not installed"
```bash
pip install pywin32
```
This server requires Windows. It will not work on macOS or Linux.

### "Failed to connect to CATIA V5"
1. Make sure CATIA V5 is running
2. Register CATIA as COM server: navigate to `C:\Program Files\Dassault Systemes\B<version>\<os>\code\bin\` and run `cnext.exe /regserver`
3. Check that no modal dialog is blocking CATIA

### "No active document"
Create or open a document first using `catia_new_part` or `catia_open_document`.

### COM ByRef array limitations
Some measurement methods may not work with late binding. If you encounter issues, try using `pycatia` as an alternative backend (contribution welcome).

## Contributing

This project is open-source. Contributions welcome:

- **Wireframe & Surface (GSD)** tools
- **Drawing** tools (2D drafting)
- **Knowledgeware** (formulas, rules, check)
- **pycatia backend** as alternative to raw win32com
- **Tests** with COM mocking
- **3DEXPERIENCE** CATIA support

## License

MIT

## Credits

Inspired by:
- [SolidWorks-MCP](https://github.com/Sam-Of-The-Arth/SolidWorks-MCP)
- [freecad-mcp](https://github.com/contextform/freecad-mcp)
- [abaqus-mcp-server](https://github.com/jianzhichun/abaqus-mcp-server)
- [pycatia](https://github.com/evereux/pycatia)
