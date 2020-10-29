#!/usr/bin/python3 -u

import os.path
import pathlib
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
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = pathlib.Path(tmpdir)
            directory = tmpdir.joinpath("directory")
            directory.mkdir()
            hidden_directory = tmpdir.joinpath(".hidden_directory")
            hidden_directory.mkdir()

            write_prf(tmpdir, ".hidden_file")
            write_prf(directory, ".nested_hidden_file")
            write_prf(hidden_directory, "ignored_file")

            file1 = write_prf(tmpdir, "file1")
            file2 = write_prf(tmpdir, "file2")
            file3 = write_prf(tmpdir, "file3")
            file4 = write_prf(directory, "file4")
            self.assertListEqual(list(bli.list_local_files(tmpdir)), [("file1", bli._md5(file1)),
                                                                      ("file2", bli._md5(file2)),
                                                                      ("file3", bli._md5(file3)),
                                                                      ("directory/file4", bli._md5(file4))])

            bli.create_bucket(bucket_name)
            bli.check_bucket(bucket_name)
            bli.upload_files(bucket_name, tmpdir)
            self.assertListEqual(list(bli.list_remote_files(bucket_name)), [("directory/file4", bli._md5(file4)),
                                                                            ("file1", bli._md5(file1)),
                                                                            ("file2", bli._md5(file2)),
                                                                            ("file3", bli._md5(file3))])
            bli.delete_files(bucket_name)
            self.assertListEqual(list(bli.list_remote_files(bucket_name)), [])
            bli.delete_bucket(bucket_name)

    def test_md5(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertEqual(bli._md5(write_prf(tmpdir, "dummy")), "dc66e4a23e6b7873679da03302c37331")


unittest.main(verbosity=2)
