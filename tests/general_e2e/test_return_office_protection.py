import os
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile
from tests.general_e2e.test_run_general_e2e import MODULE

class ReturnOfficeProtectionTests(unittest.TestCase):
    def test_import_seals_named_and_opaque_copies_without_changing_bytes_or_modes(self):
        with tempfile.TemporaryDirectory() as d:
            stage=Path(d).resolve()/'.fixture.pending-test';stage.mkdir();data=b'PK\x03\x04canonical frozen bytes'
            members={};entries=[]
            for name in ('unit/evidence/input.xlsx','scoring/trace/bindings/01-original.bin','unit/evidence/.DS_Store','unit/evidence/native.jsonl'):
                info=zipfile.ZipInfo(name);info.external_attr=(stat.S_IFREG|0o444)<<16
                members[name]=(info,data);entries.append({'path':name,'kind':'file'})
            try:
                MODULE.extract_verified_return({'members':members,'manifest':{'entries':entries},'manifest_bytes':b'{}','receipt_bytes':b'{}'},stage)
                for name in members:
                    path=stage/name;self.assertEqual(path.read_bytes(),data);self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o444)
                    if hasattr(os,'chflags') and (path.suffix in ('.xlsx','.bin') or path.name=='.DS_Store'):
                        self.assertTrue(path.stat().st_flags & stat.UF_IMMUTABLE)
            finally:MODULE._remove_import_staging(stage)
            self.assertFalse(stage.exists())

    def test_cleanup_refuses_published_tree_and_never_unlocks_symlink_target(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);published=root/'published';published.mkdir();outside=published/'input.bin';outside.write_bytes(b'original')
            if hasattr(os,'chflags'):os.chflags(outside,stat.UF_IMMUTABLE)
            try:
                with self.assertRaisesRegex(MODULE.FlowError,'NOT_OWNED'):MODULE._remove_import_staging(published)
                stage=root/'.fixture.pending-test';stage.mkdir();(stage/'outside').symlink_to(published,target_is_directory=True)
                MODULE._remove_import_staging(stage)
                self.assertEqual(outside.read_bytes(),b'original')
                if hasattr(os,'chflags'):self.assertTrue(outside.stat().st_flags & stat.UF_IMMUTABLE)
            finally:
                if hasattr(os,'chflags'):os.chflags(outside,0)
