#!/usr/bin/python3 -u

import os.path
import pathlib
import tempfile
import unittest

import prfg

import bli

bucket_name = "test.mazerty.fr"


class TestCase(unittest.TestCase):
    def test_bucket(self):
        bli.create_bucket(bucket_name)
        bli.check_bucket(bucket_name)
        bli.delete_bucket(bucket_name)

    def test_md5(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dummy = pathlib.Path(os.path.join(tmpdir, "dummy"))
            dummy.write_bytes(prfg.pseudo_random_bytearray("dummy", 1000))
            self.assertEqual(bli._md5(dummy), "dc66e4a23e6b7873679da03302c37331")


unittest.main(verbosity=2)
