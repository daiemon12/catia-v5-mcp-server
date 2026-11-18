# Create a disposable Point test document

No binary CATPart is committed. On the configured B30 installation:

1. Attach to the already configured bridge instance, or explicitly launch with
   a CATEnv derived from your normal environment as described in `docs/caa-point.md`.
2. Create a new Part and an ordinary root Geometrical Set named `DemoGeometry`.
3. Manually save it to a new local writable CATPart path and keep it active.
4. Obtain the exact CNEXT PID. Pass it with the absolute document path, set name,
   a new point name and `x_mm=10, y_mm=20, z_mm=30`.
5. Request a read-only preview. Review the plan and use its one-time token for
   confirmed execution. Verify one new point in the target set, three coordinate
   length parameters with those values, and native coordinate readback.
6. Save manually only if desired. The tool never opens, saves or closes documents.

The total `Part.Parameters.Count` can also include the point's activity parameter;
verify the three named coordinate length parameters rather than requiring a
count increase of exactly three. Repeated tests need a new point name or sample;
consumed preview tokens cannot be replayed. The original locally validated Clean
sample is retained privately and is not included in the PR.
