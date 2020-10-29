#!/usr/bin/python3 -u

import os.path
import tempfile
import unittest

import prbg

import bli

bucket_name = "test.mazerty.fr"


def write_prf(directory, name, size=1000):
    path = os.path.join(directory, name)
    prbg.prbg_to_file(name, size, path)
    return path


class TestCase(unittest.TestCase):
    def test_bucket(self):
        bli.create_bucket(bucket_name)
        bli.check_bucket(bucket_name)
        bli.delete_bucket(bucket_name)

    def test_md5(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertEqual(bli._md5(write_prf(tmpdir, "dummy")), "dc66e4a23e6b7873679da03302c37331")


unittest.main(verbosity=2)
