"""PyInstaller entry script for the frozen LocalDrop server.

PyInstaller runs its entry script as a top-level module, so pointing it straight
at `localdrop/launcher.py` makes that file the script — and every relative
import inside it (`from .__about__ import ...`) fails with "attempted relative
import with no known parent package".

This shim imports the package properly instead:

    from localdrop.launcher import main
    main()

Kept deliberately tiny: everything interesting lives in the package, and the
console script installed by pip is `localdrop = localdrop.launcher:main`, i.e.
exactly this call.
"""

from __future__ import annotations

import multiprocessing
import sys

if __name__ == "__main__":
    # Required before anything spawns a process in a frozen build; without it
    # a child process re-runs this shim instead of the real target.
    multiprocessing.freeze_support()
    from localdrop.launcher import main

    sys.exit(main())
