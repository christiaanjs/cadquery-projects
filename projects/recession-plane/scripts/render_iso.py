"""Optional annotated pyvista render. Needs: pip install -e .[pyvista]"""
import runpy
from pathlib import Path

import cadquery as cq
import numpy as np
import pyvista as pv

HERE = Path(__file__).resolve().parent
g = runpy.run_path(str(HERE.parent / "models" / "recession_plane.py"),
                   init_globals={"show_object": lambda *a, **k: None})
b = cq.Solid.extrudeLinear(g["wall_face"], cq.Vector(150,0,0))
verts, tris = b.tessellate(0.5)
V = np.array([v.toTuple() for v in verts])/100
faces = np.hstack([[3,*t] for t in tris])
bld = pv.PolyData(V, faces)
ymin,ymax,xmax = -0.8,3.8,4.7
plane = pv.PolyData(np.array([(0,ymin,2.5),(xmax,ymin,2.5+xmax),(xmax,ymax,2.5+xmax),(0,ymax,2.5)],float),[4,0,1,2,3])
ground = pv.Plane(center=(3.0,(ymin+ymax)/2,0),i_size=6.0,j_size=ymax-ymin)
p = pv.Plotter(off_screen=True, window_size=(1600,1300))
p.set_background("white")
p.add_mesh(ground, color="#b8cc9a", opacity=0.6)
p.add_mesh(bld, color="#d2bf9f", ambient=0.45, diffuse=0.6)
p.add_mesh(plane, color="#3d85d8", opacity=0.35, show_edges=True, edge_color="#1f5fa8", line_width=2)
p.add_mesh(bld.extract_feature_edges(30), color="#3b3024", line_width=3)
# trace of the plane directly above the wall line
ss=np.linspace(0,g["WALL_LEN"],50); tr=np.array([(g["wall_xy"](t)[0]/100,g["wall_xy"](t)[1]/100,2.5+g["wall_xy"](t)[0]/100) for t in ss])
p.add_mesh(pv.lines_from_points(tr), color="#1f5fa8", line_width=4)
for t in (0,g["WALL_LEN"]):
    x,y=g["wall_xy"](t); x/=100;y/=100
    p.add_mesh(pv.Line((x,y,g["roof_z"](t)/100),(x,y,2.5+x)), color="#1f5fa8", line_width=2)
p.add_mesh(pv.Line((0,ymin,0),(0,ymax,0)), color="red", line_width=5)
p.add_mesh(pv.Line((0,ymin,0),(0,ymin,2.5)), color="red", line_width=3)
xp,yp = g["wall_xy"](g["S_PEAK"]); xp/=100; yp/=100
p.add_mesh(pv.Line((xp,yp,4.75),(xp,yp,2.5+xp)), color="black", line_width=6)
p.add_point_labels(np.array([(0,ymax,0),(0,ymin,1.25),(xp,yp,4.85),(0.6,ymax,3.1)]),
  ["Western boundary","2.5 m","Peak: 10 cm clearance","45° recession plane"],
  font_size=22, point_size=1, shape_opacity=0.8, always_visible=True)
p.add_axes(xlabel="E", ylabel="N", zlabel="Up")
p.enable_parallel_projection()
c = np.array([2.6,1.5,3.2])
p.camera.focal_point = c; p.camera.position = c + 20*np.array([-1,-0.75,0.9]); p.camera.up=(0,0,1)
p.reset_camera(); p.camera.zoom(1.0)
p.screenshot(str(HERE.parent / "recession_iso.png"))
