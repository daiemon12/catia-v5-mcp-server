"""Capture verification screenshots for PR #15:
  1. CATIA specification tree showing the mechanism
  2. Assembly at 90-degree drive position

Usage:
    python scripts/capture_90deg_screenshots.py

Prerequisites:
    - CATIA V5 running with an assembly containing two parts
    - Each part has Geometrical Set "KinGeo" with standalone Line.1
    - Line.1 must be normal to the reference plane (e.g., YZ plane)
"""

import asyncio
import io
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
ARTIFACT_DIR = os.path.join(SERVER_DIR, "artifacts")
os.makedirs(ARTIFACT_DIR, exist_ok=True)

HELP = r"F:\Openwork\test_output\KIN_LineRef.CATPart"


async def main():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "catia_mcp.server"],
        cwd=SERVER_DIR,
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            def show(label, res):
                text = res.content[0].text if res.content else str(res)
                print(f"\n=== {label} ===\n{text}")
                return text

            # Close any existing product documents
            for i in range(10):
                try:
                    await session.call_tool(
                        "catia_close_document", {"name": "Product1.CATProduct"}
                    )
                except Exception:
                    pass
                try:
                    await session.call_tool(
                        "catia_close_document", {"name": "Product2.CATProduct"}
                    )
                except Exception:
                    pass

            # Create fresh assembly
            print("\n--- Step 1: Create fresh assembly ---")
            new_prod = await session.call_tool(
                "catia_new_product", {"name": "MechTest"}
            )
            print(new_prod.content[0].text)

            # Add two helper components
            print("\n--- Step 2: Add components ---")
            await session.call_tool("catia_add_component", {"file_path": HELP})
            await session.call_tool("catia_add_component", {"file_path": HELP})

            # Create revolute joint WITH command_angle_deg so we can drive it
            print("\n--- Step 3: Create revolute joint with angle command ---")
            create_rev = await session.call_tool(
                "catia_kin_create_revolute_joint",
                {
                    "component_a": "Part1.1",
                    "component_b": "Part1.2",
                    "plane_element": "yz plane",
                    "command_angle_deg": 0.0,
                },
            )
            print(create_rev.content[0].text)

            # Drive to 90°
            print("\n--- Step 4: Drive mechanism to 90 degrees ---")
            drive90 = await session.call_tool(
                "catia_kin_drive_mechanism", {"angle_deg": 90.0}
            )
            print(drive90.content[0].text)

    # Give CATIA time to update the 3D display
    print("\nWaiting for CATIA display to update...")
    await asyncio.sleep(3)

    # Capture screenshots
    print("\n--- Step 5: Capture screenshots ---")
    try:
        from PIL import ImageGrab

        # Screenshot 1: Full screen (spec tree + 3D view)
        img1 = ImageGrab.grab()
        path1 = os.path.join(ARTIFACT_DIR, "spec_tree_90deg.png")
        img1.save(path1)
        print(f"Saved: {path1} ({img1.size[0]}x{img1.size[1]})")

        # Brief pause
        time.sleep(1)

        # Screenshot 2: Another capture (assembly at 90°)
        img2 = ImageGrab.grab()
        path2 = os.path.join(ARTIFACT_DIR, "assembly_90deg.png")
        img2.save(path2)
        print(f"Saved: {path2} ({img2.size[0]}x{img2.size[1]})")

        print("\nScreenshot capture complete.")

    except ImportError:
        print("PIL not available. Install with: pip install pillow")
    except Exception as e:
        print(f"Screenshot capture failed: {e}")


asyncio.run(main())
