/* Read-only loader feasibility probe. No hooks, paths, credentials or app edits. */
#include <unistd.h>

__attribute__((constructor)) static void loaded(void) {
  static const char marker[] = "MEMORY_E2E_LOADER_PROBE_LOADED\n";
  (void)write(STDERR_FILENO, marker, sizeof(marker) - 1);
}
