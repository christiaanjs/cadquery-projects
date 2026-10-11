"""
Western wall vs 45° @ 2.5 m recession plane (western boundary).
Units: cm. Coordinates: x = east, perpendicular distance from boundary
(boundary is x = 0), y = north, z = up from ground at the boundary.
"""
import math

import cadquery as cq

# ---- Measurements from the sketch -------------------------------------
X_NORTH = 166.0      # boundary -> north end of west wall
X_SOUTH = 295.0      # boundary -> south end of west wall
WALL_LEN = 328.0     # length along the wall
PEAK_FROM_SOUTH = 152.0
H_NORTH = 310.0      # north eave height
H_PEAK = 475.0       # ridge height
H_SOUTH = H_NORTH    # eaves are level; pitches differ N vs S
S_PEAK = WALL_LEN - PEAK_FROM_SOUTH                      # from north end
pitch = (H_PEAK - H_NORTH) / S_PEAK                      # north slope

DEPTH = 600.0        # how far east to extrude the building (arbitrary)

# ---- Recession plane: z = 250 + 1.0 * x  (45°, 2.5 m at boundary) ----
R_START, R_SLOPE = 250.0, math.tan(math.radians(45))

# ---- Geometry ----------------------------------------------------------
dx = X_SOUTH - X_NORTH
dy = math.sqrt(WALL_LEN**2 - dx**2)          # N–S extent of the wall


def wall_xy(s):
    """Plan position of a point s cm along the wall from the north end."""
    t = s / WALL_LEN
    return X_NORTH + dx * t, dy * (1 - t)


def roof_z(s):
    if s <= S_PEAK:
        return H_NORTH + pitch * s
    return H_PEAK - (H_PEAK - H_SOUTH) * (s - S_PEAK) / PEAK_FROM_SOUTH


profile_s = [0, 0, S_PEAK, WALL_LEN, WALL_LEN]
profile_z = [0, H_NORTH, H_PEAK, H_SOUTH, 0]
pts = [cq.Vector(*wall_xy(s), z) for s, z in zip(profile_s, profile_z)]
wall_face = cq.Face.makeFromWires(cq.Wire.makePolygon(pts, close=True))
building = cq.Solid.extrudeLinear(wall_face, cq.Vector(DEPTH, 0, 0))

# Region ABOVE the recession plane (a wedge, extruded N–S)
big = 2000.0
wedge_pts = [(-big, R_START - big * R_SLOPE), (big, R_START + big * R_SLOPE),
             (big, 3 * big), (-big, 3 * big)]
above_plane = (cq.Workplane("XZ").polyline(wedge_pts).close()
               .extrude(-big - dy).translate((0, -big / 2, 0)).val())

breach = building.intersect(above_plane)

# ---- Report ------------------------------------------------------------
print(f"Wall N–S extent: {dy:.1f}  |  south eave: {H_SOUTH:.1f}")
print(f"{'point':<8}{'x':>8}{'height':>9}{'plane':>9}{'clear':>9}")
for name, s in [("north", 0), ("peak", S_PEAK), ("south", WALL_LEN)]:
    x, _ = wall_xy(s)
    plane = R_START + R_SLOPE * x
    print(f"{name:<8}{x:8.1f}{roof_z(s):9.1f}{plane:9.1f}{plane - roof_z(s):9.1f}")

vol = breach.Volume()
if vol < 1e-3:
    print("\nNo intersection: building is entirely under the recession plane.")
else:
    bb = breach.BoundingBox()
    print(f"\nBreach volume: {vol / 1e6:.3f} m³")
    print(f"Breach extents x {bb.xmin:.1f}–{bb.xmax:.1f}, "
          f"y {bb.ymin:.1f}–{bb.ymax:.1f}, z {bb.zmin:.1f}–{bb.zmax:.1f}")

# ---- Display ---------------------------------------------------------------
# project.toml sets units = "cm", so cqp scales everything to mm on export.
Y0, Y1 = -100.0, dy + 100.0          # N–S extent of plane/boundary
X1 = X_SOUTH + DEPTH                  # how far east to draw the plane

plane_face = cq.Face.makeFromWires(cq.Wire.makePolygon([
    cq.Vector(0, Y0, R_START), cq.Vector(X1, Y0, R_START + R_SLOPE * X1),
    cq.Vector(X1, Y1, R_START + R_SLOPE * X1), cq.Vector(0, Y1, R_START),
], close=True))
boundary_line = cq.Edge.makeLine(cq.Vector(0, Y0, 0), cq.Vector(0, Y1, 0))
# Vertical face on the boundary from ground up to the 2.5 m start height
boundary_face = cq.Face.makeFromWires(cq.Wire.makePolygon([
    cq.Vector(0, Y0, 0), cq.Vector(0, Y1, 0),
    cq.Vector(0, Y1, R_START), cq.Vector(0, Y0, R_START),
], close=True))

show_object(building, name="building", options={"color": "#d1bf9e"})
show_object(plane_face, name="recession_plane", options={"color": "#3d85d8", "alpha": 0.4})
show_object(boundary_face, name="boundary_2.5m", options={"color": "#e63333", "alpha": 0.3})
show_object(boundary_line, name="boundary_line", options={"color": "#ff0000"})
if vol > 1e-3:
    show_object(breach, name="breach", options={"color": "#ff0000"})
