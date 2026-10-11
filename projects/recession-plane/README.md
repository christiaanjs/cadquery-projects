# Recession plane check

Checks the western wall (and roof) of a building against a 45° recession plane that starts at
2.5 m above ground on the western boundary. Measurements come from a site sketch; the model
reports clearance at the north eave, the ridge and the south eave, and builds the breach solid
(if any) where the building pokes above the plane.

## Status
**modelling**

## Dimensions
- Units: cm (cqp converts to mm for exports and the viewer)
- Coordinates: x = east from the boundary, y = north, z = up
- Wall length 328, ridge 475, eaves 310; plane z = 250 + x

## Notes
- `python -m cqp build recession-plane` prints the clearance table and breach volume.
- `scripts/render_iso.py` is an optional annotated pyvista render
  (`pip install -e .[pyvista]`, then `python projects/recession-plane/scripts/render_iso.py`).
