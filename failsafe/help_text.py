# SPDX-License-Identifier: GPL-3.0-or-later
"""One plain-English "why it matters" line per check.

Shown in the panel only when the user turns on "Explain" (off by default, so the
normal problem view stays uncluttered). This is the rationale — what the check
means and why you'd care — which is different from a finding's message (what is
wrong right now) and its Tip (how to fix it).

Wording is deliberately hedged ("can", "may"): most of these conditions are
*risks*, not guaranteed failures, and some are legitimate in certain workflows.
Overstating them would undermine the tool's trust story.
"""

HELP = {
    1: ("Physics uses an object's transforms and mesh. Unapplied scale — and "
        "some rotation setups — can make a simulation behave unexpectedly, so "
        "it's worth applying them before baking."),
    2: ("Mass sets how a rigid body responds to forces and collisions. A value "
        "far off for its size can make it behave oddly — drifting, or pushing "
        "hard into other objects."),
    3: ("Rigid bodies that already overlap on the first frame can suddenly push "
        "apart or jitter as the simulation starts."),
    4: ("A Convex Hull shape approximates the outside of an object and can't "
        "represent hollow or concave regions. A Mesh or compound shape may suit "
        "the body's role better."),
    5: ("Collision surfaces that are very dense, or have internal/overlapping "
        "faces, can make a simulation slow or unstable."),
    6: ("A rigid body is only simulated if a Rigid Body World exists, is "
        "enabled, and contains it. (You can still move objects with animation "
        "instead.)"),
    7: ("Cloth and soft bodies only collide with objects that have a Collision "
        "modifier. Without one, they can fall straight through."),
    8: ("Negative or parent-inherited scale can invert normals and distort an "
        "object's collision size, so physics may behave unexpectedly."),
    9: ("Blender's physics has scale-dependent tolerances. Very tiny or very "
        "large objects can simulate less stably than roughly human-scale ones."),
    10: ("For mesh-based rigid-body shapes, Blender uses the object origin as "
         "the centre of mass. An offset origin can change how the body rotates; "
         "primitive shapes behave differently."),
    11: ("Collision margin adds a small tolerance that helps stability. Some "
         "shapes embed it, but if it's too large others can show a visible gap."),
    12: ("An animated passive collider usually needs the 'Animated' option, or "
         "its collision shape may stay frozen at the start frame."),
    13: ("A rigid-body constraint (a hinge or chain link) needs two properly "
         "set-up bodies, or it holds nothing together."),
    14: ("On a collider, the Collision modifier should sit below any deforming "
         "modifiers, or cloth may collide with the undeformed shape."),
    15: ("A cloth pin group holds the chosen vertices in place. If pinning is "
         "intended but the group is empty or missing, the whole cloth can drop."),
    16: ("A fluid domain only fills from a Flow or Inflow source inside it. If "
         "you expect fluid but see none, check the source."),
    17: ("An unbaked simulation is recomputed at render time, so it can differ "
         "from the viewport — or stall a render farm. Some workflows recalculate "
         "on purpose."),
    18: ("Blender can still report 'baked' after the cache files are gone. "
         "Disk-backed caches need their files present; in-memory and packed "
         "bakes are the exceptions."),
    19: ("If the bake stops before the last rendered frame, the simulation can "
         "freeze or look wrong past that point."),
    20: ("A missing required cache frame can cause a freeze or jump at that "
         "point in the render."),
    21: ("Two simulations pointing at the same cache location can overwrite each "
         "other's frames, unless their cache names differ."),
    22: ("A cache saved outside the project may not be found on another machine "
         "or a render farm, unless the path is still reachable there."),
    23: ("Changing scene timing or simulation speed after baking can make the "
         "existing cache play back wrong. Blender doesn't always record enough "
         "to confirm the original bake settings."),
}
