# SPDX-License-Identifier: GPL-3.0-or-later
"""Physics Preflight — a read-only Blender extension that catches physics and
simulation-cache problems before you render.

23 checks in two groups (Physics Setup, Simulation Caches). The cache checks
verify the actual files on disk instead of trusting Blender's "baked" flags,
which stay True after the cache files are gone.
"""
from . import operators
from . import ui

# Importing the check modules registers every check into engine.CHECKS via the
# @check decorator. Keep these imports — removing them hides the checks.
from . import checks_setup  # noqa: F401
from . import checks_cache   # noqa: F401


def register():
    operators.register()
    ui.register()


def unregister():
    ui.unregister()
    operators.unregister()
