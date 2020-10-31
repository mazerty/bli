#!/usr/bin/python3 -u

import os.path
import pathlib
import tempfile
import unittest

import prbg

import bli

bucket_name = "test.mazerty.fr"
result = {("file1", "e382ac6f66df7fb71dae6292810182eb"),
          ("file2", "260b6f5bf4fdfe7be7cea1737b41e797"),
          ("file3", "7d5f31ffd43f957a4f4f8982ef65b12d"),
          ("directory/file4", "803ab14c32a1b1cdf9b19d7417908e43")}


def _write_prf(directory, name, size=1000):
    path = os.path.join(directory, name)
    prbg.prbg_to_file(name, size, path)
    return path


class TestCase(unittest.TestCase):
    def test_bucket(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = pathlib.Path(tmpdir)
            directory = tmpdir.joinpath("directory")
            directory.mkdir()
            hidden_directory = tmpdir.joinpath(".hidden_directory")
            hidden_directory.mkdir()

            _write_prf(tmpdir, ".hidden_file")
            _write_prf(directory, ".nested_hidden_file")
            _write_prf(hidden_directory, "ignored_file")

            _write_prf(tmpdir, "file1")
            _write_prf(tmpdir, "file2")
            _write_prf(tmpdir, "file3")
            _write_prf(directory, "file4")
            self.assertSetEqual(set(bli._yield_local_relative_paths_md5(tmpdir)), result)

            bli.create_bucket(bucket_name)
            bli.upload_files(bucket_name, tmpdir)
            self.assertSetEqual(set(bli._yield_remote_relative_paths_md5(bucket_name)), result)

        with tempfile.TemporaryDirectory() as tmpdir:
            bli.download_files(bucket_name, tmpdir)
            self.assertSetEqual(set(bli._yield_local_relative_paths_md5(tmpdir)), result)

        bli.delete_files(bucket_name)
        self.assertSetEqual(set(bli._yield_remote_relative_paths_md5(bucket_name)), set())
        bli.delete_bucket(bucket_name)

    def test_md5(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertEqual(bli._md5(_write_prf(tmpdir, "dummy")), "dc66e4a23e6b7873679da03302c37331")


unittest.main(verbosity=2)
