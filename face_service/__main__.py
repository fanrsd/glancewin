import os
# OpenCV's DNN backend spawns one thread per core by default; those threads
# compete with the pipe server for CPU during a verify. One is enough at
# 80x80 (liveness) and 112x112 (SFace) input sizes.
os.environ.setdefault("OMP_NUM_THREADS", "1")

import multiprocessing

from .service import main

if __name__ == "__main__":
    # On Windows, freeze_support prevents child processes from re-running main
    # when a module uses multiprocessing.Process without the __main__ guard.
    multiprocessing.freeze_support()
    main()
