# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings baseline — an OPT-IN, read-only drift check.

The design decision (approved): Failsafe scans stay 100% read-only and NEVER
write anything into the customer's .blend. The one thing that can write is the
*user-clicked* "Save Baseline" action, and it writes only a small EXTERNAL JSON
file next to the .blend. A later scan reads that file and reports whether the
simulation settings changed since it was saved.

Honesty rules baked in here:
  * No baseline, unreadable baseline, or a simulation whose identity doesn't
    match the baseline  ->  "Couldn't verify" (UNKNOWN), never PASS.
  * A match means "settings unchanged since the baseline was saved" — it is NOT
    proof the bake is good, and we never claim "unchanged since bake" (we can't
    know the baseline was taken right after a successful bake).
  * Saving a baseline is always explicit; nothing is captured or overwritten
    automatically.

The baseline file is plain JSON so it's auditable and diffable.
"""
import json
import os
import time

import bpy


BASELINE_SCHEMA = 1

# Curated, version-tolerant settings per simulation type. Missing attributes on a
# given Blender build are simply skipped (never an error), so the fingerprint
# degrades gracefully across versions.
_CLOTH = ["quality", "mass", "air_damping", "bending_model", "tension_stiffness",
          "compression_stiffness", "shear_stiffness", "bending_stiffness",
          "use_pressure", "uniform_pressure_force", "use_sewing_springs"]
_CLOTH_COLL = ["collision_quality", "distance_min", "use_collision",
               "use_self_collision", "self_distance_min"]
_SOFTBODY = ["mass", "speed", "goal_default", "goal_spring", "pull", "push",
             "bend", "plastic", "friction", "use_goal", "use_edges"]
_FLUID = ["resolution_max", "time_scale", "cfl_condition", "use_adaptive_domain",
          "use_noise", "noise_scale", "use_mesh", "viscosity_value",
          "use_diffusion", "domain_type", "use_guide"]
_PARTICLE = ["count", "frame_start", "frame_end", "lifetime", "mass", "timestep",
             "subframes"]
_RBW = ["time_scale", "substeps_per_frame", "solver_iterations"]


def _rv(v):
    """Normalise a value for stable comparison: round floats, pass ints/bools/
    strings, stringify anything exotic."""
    if isinstance(v, bool):
        return v
    if isinstance(v, float):
        return round(v, 5)
    if isinstance(v, (int, str)):
        return v
    try:
        return round(float(v), 5)
    except (TypeError, ValueError):
        return str(v)


def _sample(owner, attrs):
    out = {}
    if owner is None:
        return out
    for a in attrs:
        if hasattr(owner, a):
            try:
                out[a] = _rv(getattr(owner, a))
            except Exception:
                continue
    return out


def _cache_range_point(pc, scene):
    try:
        return [int(getattr(pc, "frame_start", scene.frame_start)),
                int(getattr(pc, "frame_end", scene.frame_end))]
    except Exception:
        return None


def capture_fingerprints(scene):
    """Walk the scene and return {identity: {system, kind, settings, cache_range}}.
    Pure read — touches nothing. Identity is 'ObjectName::System'."""
    fp = {}

    def add(obj_name, system, kind, settings, crange):
        fp["%s::%s" % (obj_name, system)] = {
            "system": system, "kind": kind,
            "settings": settings, "cache_range": crange,
        }

    for obj in scene.objects:
        for mod in obj.modifiers:
            if mod.type == "CLOTH":
                s = _sample(getattr(mod, "settings", None), _CLOTH)
                s.update({"coll_%s" % k: v for k, v in
                          _sample(getattr(mod, "collision_settings", None),
                                  _CLOTH_COLL).items()})
                add(obj.name, "Cloth", "point", s,
                    _cache_range_point(getattr(mod, "point_cache", None), scene))
            elif mod.type == "SOFT_BODY":
                s = _sample(getattr(mod, "settings", None), _SOFTBODY)
                add(obj.name, "Soft Body", "point", s,
                    _cache_range_point(getattr(mod, "point_cache", None), scene))
            elif mod.type == "FLUID":
                if getattr(mod, "fluid_type", "") == "DOMAIN":
                    ds = getattr(mod, "domain_settings", None)
                    s = _sample(ds, _FLUID)
                    cr = None
                    if ds is not None:
                        try:
                            cr = [int(getattr(ds, "cache_frame_start",
                                              scene.frame_start)),
                                  int(getattr(ds, "cache_frame_end",
                                              scene.frame_end))]
                        except Exception:
                            cr = None
                    add(obj.name, "Fluid", "fluid", s, cr)
        if obj.type == "MESH":
            for psys in obj.particle_systems:
                st = psys.settings
                if st is None or st.type != "EMITTER":
                    continue
                s = _sample(st, _PARTICLE)
                add(obj.name, "Particles", "point", s,
                    _cache_range_point(getattr(psys, "point_cache", None), scene))

    rbw = getattr(scene, "rigidbody_world", None)
    if rbw is not None:
        s = _sample(rbw, _RBW)
        add("Scene", "Rigid Body World", "rbw", s, None)
    return fp


def default_baseline_path():
    """`<blenddir>/<blendbasename>.failsafe-baseline.json`, or None if unsaved."""
    fp = bpy.data.filepath
    if not fp:
        return None
    d = os.path.dirname(bpy.path.abspath(fp))
    base = os.path.splitext(os.path.basename(fp))[0]
    return os.path.join(d, base + ".failsafe-baseline.json")


def save_baseline(scene, path, overwrite=False):
    """Write the baseline JSON. User-initiated only. Returns the path written.

    This is the ONE action in the whole add-on that writes a file, and it writes
    only this external sidecar — never the .blend.

    It never writes automatically and never silently replaces an existing
    baseline: if ``path`` already exists and ``overwrite`` is False, it raises
    ``FileExistsError`` so the caller (the operator) can ask the user first."""
    if os.path.exists(path) and not overwrite:
        raise FileExistsError(
            "a baseline already exists at %s (pass overwrite=True to replace it)"
            % path)
    data = {
        "tool": "failsafe", "schema": BASELINE_SCHEMA, "kind": "baseline",
        "blender": bpy.app.version_string,
        "file": bpy.data.filepath or None,
        "saved_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "fingerprints": capture_fingerprints(scene),
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
    return path


def load_baseline(path):
    """Return the parsed baseline dict, or raise ValueError if missing/invalid."""
    if not path or not os.path.isfile(path):
        raise ValueError("no baseline file")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise ValueError("baseline unreadable: %s" % exc)
    if not isinstance(data, dict) or data.get("kind") != "baseline" \
            or not isinstance(data.get("fingerprints"), dict):
        raise ValueError("not a Failsafe baseline file")
    return data


def schema_ok(data):
    """True if the baseline's schema is one this build knows how to compare.
    A newer/unknown schema -> caller reports 'Couldn't verify', never a guess."""
    return isinstance(data, dict) and data.get("schema") == BASELINE_SCHEMA


def foreign_file_name(data, current_filepath):
    """If this baseline records a DIFFERENT source .blend than ``current_filepath``,
    return the baseline's recorded filename; otherwise None.

    Compared by *filename* so moving a project folder (same .blend name) doesn't
    trip it, while a baseline copied in from another scene (different name) is
    caught and reported as 'Couldn't verify' instead of a confident result."""
    saved_file = data.get("file")
    if not saved_file or not current_filepath:
        return None
    sb = os.path.basename(str(saved_file))
    cb = os.path.basename(str(current_filepath))
    if sb and cb and sb != cb:
        return sb
    return None


def diff_fingerprint(saved_fp, current_fp):
    """Keys whose value changed between two fingerprint dicts (settings +
    cache_range). Returns a sorted list of changed setting names."""
    changed = []
    s_set = saved_fp.get("settings", {}) if isinstance(saved_fp, dict) else {}
    c_set = current_fp.get("settings", {}) if isinstance(current_fp, dict) else {}
    for k in set(s_set) | set(c_set):
        if s_set.get(k) != c_set.get(k):
            changed.append(k)
    if saved_fp.get("cache_range") != current_fp.get("cache_range"):
        changed.append("cache frame range")
    return sorted(changed)
