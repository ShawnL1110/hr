import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
spec=importlib.util.spec_from_file_location('release',Path(__file__).parents[1]/'deploy/restricted/hr_release.py')
release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)

class ReleaseBoundaryTests(unittest.TestCase):
    def archive(self,root,entries):
        path=root/'input.tar'
        with tarfile.open(path,'w') as t:
            for name,body,kind in entries:
                m=tarfile.TarInfo(name)
                if kind=='link': m.type=tarfile.SYMTYPE;m.linkname='/etc/shadow';t.addfile(m)
                else: m.size=len(body);t.addfile(m,io.BytesIO(body))
        return path
    def test_only_hr_code_is_extracted(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);dst=root/'out';dst.mkdir()
            archive=self.archive(root,[('hr/main.py',b'pass','file'),('compose.yaml',b'host mounts','file'),('Dockerfile',b'host policy','file')])
            release.extract_code(archive,dst)
            self.assertTrue((dst/'hr/main.py').exists());self.assertFalse((dst/'compose.yaml').exists());self.assertFalse((dst/'Dockerfile').exists())
    def test_traversal_and_links_and_secrets_rejected(self):
        for name,kind in [('../etc/passwd','file'),('/etc/passwd','file'),('hr/escape','link'),('hr/.env','file'),('hr/server.pem','file')]:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as d:
                root=Path(d);dst=root/'out';dst.mkdir()
                with self.assertRaises(ValueError):release.extract_code(self.archive(root,[(name,b'x',kind)]),dst)
