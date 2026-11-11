# SPDX-License-Identifier: GPL-3.0-or-later
"""One plain-English "why it matters" line per check.

Shown in the panel only when the user turns on "Explain" (off by default, so the
normal problem view stays uncluttered). This is the rationale — what the check
means and why you'd care — which is different from a finding's message (what is
wrong right now) and its Tip (how to fix it). Written for someone new to
Blender's physics, without jargon.
"""

HELP = {
    1: ("Physics uses an object's real size and pose. Unapplied scale or "
        "rotation makes collisions and cloth behave as if the object were a "
        "different size or angle than it looks."),
    2: ("Mass decides how heavy a rigid body feels. A value far off for its "
        "size makes it drift like a balloon or smash through things."),
    3: ("Rigid bodies that already overlap on the first frame get shoved apart "
        "violently as the sim starts."),
    4: ("A Convex Hull collision shape fills in any hollow, so cups, bowls and "
        "rooms act solid. Hollow shapes need a Mesh shape instead."),
    5: ("Collision surfaces that are very dense or have internal/overlapping "
        "faces make a simulation slow and jittery."),
    6: ("Rigid bodies only move if a Rigid Body World exists, is enabled, and "
        "actually contains them."),
    7: ("Cloth and soft bodies only land on objects that have a Collision "
        "modifier. Without one, they fall straight through."),
    8: ("Negative or parent-inherited scale flips an object's normals and "
        "distorts its collision size, so physics behaves backwards."),
    9: ("Blender's solver is tuned around 1-metre objects. Very tiny or very "
        "huge objects simulate unstably."),
    10: ("A rigid body spins around its origin. An origin far from the shape "
         "makes it tumble off-centre."),
    11: ("The collision margin is an invisible buffer around a body. Too large, "
         "and objects float with a visible gap."),
    12: ("A passive collider that is animated must be marked 'Animated', or its "
         "collision shape stays frozen at the start frame."),
    13: ("A rigid-body constraint (a hinge or chain link) needs two valid "
         "bodies, or it silently holds nothing together."),
    14: ("Collision must sit below any deforming modifiers, or cloth collides "
         "with the object's undeformed shape."),
    15: ("A cloth pin group holds part of the cloth in place. If it's empty or "
         "missing, the whole cloth drops."),
    16: ("A fluid domain only fills if a Flow or Inflow source sits inside it."),
    17: ("An unbaked simulation is re-computed at render time and can differ "
         "from what you see in the viewport — or freeze a render farm."),
    18: ("Blender keeps reporting 'baked' even after the cache files are gone. "
         "The render needs the actual files on disk, so Failsafe checks them."),
    19: ("If the bake stops before the last rendered frame, the simulation "
         "freezes for the rest of the shot."),
    20: ("A single missing cache frame is a freeze or pop at that exact moment "
         "in the render."),
    21: ("Two simulations pointed at the same cache folder overwrite each "
         "other's frames."),
    22: ("A cache saved outside the project folder won't be found on another "
         "machine or a render farm."),
    23: ("Blender doesn't re-time an existing bake. Changing FPS or time scale "
         "after baking makes it play back at the wrong speed."),
}
