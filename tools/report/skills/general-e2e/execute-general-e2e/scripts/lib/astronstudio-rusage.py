"""Read cumulative macOS per-process I/O counters with no elevated privileges."""
import ctypes
import json
import sys


# Darwin sys/resource.h struct rusage_info_v2, RUSAGE_INFO_V2.
class RUsage(ctypes.Structure):
    _fields_ = [("uuid", ctypes.c_ubyte * 16)] + [
        (key, ctypes.c_uint64) for key in (
            "user_time", "system_time", "pkg_idle_wkups", "interrupt_wkups",
            "pageins", "wired_size", "resident_size", "phys_footprint",
            "proc_start_abstime", "proc_exit_abstime", "child_user_time",
            "child_system_time", "child_pkg_idle_wkups", "child_interrupt_wkups",
            "child_pageins", "child_elapsed_abstime", "diskio_bytesread",
            "diskio_byteswritten",
        )
    ]


call = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True).proc_pid_rusage
call.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
call.restype = ctypes.c_int
rows = []
for value in sys.argv[1:]:
    pid = int(value)
    stats = RUsage()
    if call(pid, 2, ctypes.byref(stats)):
        rows.append({"pid": pid, "errno": ctypes.get_errno()})
    else:
        rows.append({
            "pid": pid,
            "read_bytes": stats.diskio_bytesread,
            "written_bytes": stats.diskio_byteswritten,
            "process_start_abstime": str(stats.proc_start_abstime),
        })
print(json.dumps(rows))
