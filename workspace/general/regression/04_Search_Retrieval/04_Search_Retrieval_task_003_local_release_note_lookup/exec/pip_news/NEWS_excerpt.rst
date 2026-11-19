pip release-note excerpts
=========================

Source
------

These excerpts are copied from pip's official ``NEWS.rst`` at the fixed
``23.1`` tag:

https://raw.githubusercontent.com/pypa/pip/23.1/NEWS.rst

The release headings, section headings, entries, punctuation, and references
below are unchanged. Unrelated entries from each release are omitted.

23.1 (2023-04-15)
=================

Features
--------

- Support a per-requirement ``--config-settings`` option in requirements files. (`#11325 <https://github.com/pypa/pip/issues/11325>`_)
- Add ``-C`` as a short version of the ``--config-settings`` option. (`#11786 <https://github.com/pypa/pip/issues/11786>`_)
- Add ``--keyring-provider`` flag. See the Authentication page in the documentation for more info. (`#8719 <https://github.com/pypa/pip/issues/8719>`_)

Bug Fixes
---------

- Correct the way to decide if keyring is available. (`#11774 <https://github.com/pypa/pip/issues/11774>`_)

23.0.1 (2023-02-17)
===================

Features
--------

- Ignore PIP_REQUIRE_VIRTUALENV for ``pip index`` (`#11671 <https://github.com/pypa/pip/issues/11671>`_)
- Implement ``--break-system-packages`` to permit installing packages into
  ``EXTERNALLY-MANAGED`` Python installations. (`#11780 <https://github.com/pypa/pip/issues/11780>`_)

Bug Fixes
---------

- Improve handling of isolated build environments on platforms that
  customize the Python's installation schemes, such as Debian and
  Homebrew. (`#11740 <https://github.com/pypa/pip/issues/11740>`_)
- Do not crash in presence of misformatted hash field in ``direct_url.json``. (`#11773 <https://github.com/pypa/pip/issues/11773>`_)

23.0 (2023-01-30)
=================

Features
--------

- Change the hashes in the installation report to be a mapping. Emit the
  ``archive_info.hashes`` dictionary in ``direct_url.json``. (`#11312 <https://github.com/pypa/pip/issues/11312>`_)
- Implement logic to read the ``EXTERNALLY-MANAGED`` file as specified in PEP 668.
  This allows a downstream Python distributor to prevent users from using pip to
  modify the externally managed environment. (`#11381 <https://github.com/pypa/pip/issues/11381>`_)
- Enable the use of ``keyring`` found on ``PATH``. This allows ``keyring``
  installed using ``pipx`` to be used by ``pip``. (`#11589 <https://github.com/pypa/pip/issues/11589>`_)

Bug Fixes
---------

- Fix scripts path in isolated build environment on Debian. (`#11623 <https://github.com/pypa/pip/issues/11623>`_)

22.3.1 (2022-11-05)
===================

Bug Fixes
---------

- Fix entry point generation of ``pip.X``, ``pipX.Y``, and ``easy_install-X.Y``
  to correctly account for multi-digit Python version segments (e.g. the "11"
  part of 3.11). (`#11547 <https://github.com/pypa/pip/issues/11547>`_)
