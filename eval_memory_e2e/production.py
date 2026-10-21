"""Evaluation uses the installed product; source builds are historical evidence only."""
import os

from .io import require

POLICY = 'installed-production-package-only/v1'
ASTUDIO_ADAPTER = 'macos-seatbelt-astudio-backend/v1'
ERROR = 'ASTUDIO_PRODUCTION_PACKAGE_REQUIRED'


def reject_source_build():
    require(False, ERROR, 'ACode source edits, builds, tests and replacement executors are outside evaluation scope')


def require_production_lease(lease):
    require(lease.get('contract') == ASTUDIO_ADAPTER
            and not any(key in lease for key in ('compiled_kernel', 'native_executor')),
            ERROR, 'Legacy v2/v3 leases are archived diagnostics, not production evaluation inputs')


def require_production_profile(harness, profile):
    if harness != 'AstronStudio':
        return
    protocol = profile.get('memory_protocol', {})
    boundary = profile.get('non_target_memory_boundary', {})
    require(not any(key in profile for key in ('installed_kernel_reference', 'compiled_kernel', 'native_executor'))
            and protocol.get('compiled_kernel_diagnostic') is not True
            and protocol.get('automatic_generation_diagnostic_allowed') is not True
            and boundary.get('admitted_adapter') in (None, ASTUDIO_ADAPTER),
            ERROR, 'A diagnostic/unscored label cannot admit a modified product into evaluation')


def require_production_environment(environment=None):
    environment = os.environ if environment is None else environment
    require(not any(environment.get(key) for key in ('ASTUDIO_ACODE_BIN', 'ACODE_EXEC_SERVER_URL')),
            ERROR, 'Do not inherit kernel or execution-service overrides when launching the production app')
