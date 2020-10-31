import os.path
import pathlib
import tempfile
import unittest

import prbg

import bli

bucket_name = "test.mazerty.fr"

result1 = {("file1", "e382ac6f66df7fb71dae6292810182eb"),
           ("file2", "260b6f5bf4fdfe7be7cea1737b41e797"),
           ("file3", "7d5f31ffd43f957a4f4f8982ef65b12d"),
           ("directory/file4", "803ab14c32a1b1cdf9b19d7417908e43")}
result2 = {("file1", "e382ac6f66df7fb71dae6292810182eb"),
           ("file2", "260b6f5bf4fdfe7be7cea1737b41e797"),
           ("file3", "0bc7622b9fbe4f9c5705270b22d3f683"),
           ("directory/file5", "23d235db483342f9df6200f0871dfcb2")}


def _write_prf(directory: str, name: str, size: int = 1000) -> str:
    """
    Creates a file with pseudorandom generated content using prbg.

    :param directory: parent directory
    :param name: name of the file, also the seed of the pseudorandom generator
    :param size: size of the file, defaults to 1000 bytes
    :return: full path of the generated file
    """

    path = os.path.join(directory, name)
    prbg.prbg_to_file(name, size, path)

    return path


class TestCase(unittest.TestCase):
    def test_md5(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertEqual(bli._md5(_write_prf(tmpdir, "dummy")), "dc66e4a23e6b7873679da03302c37331")

    def test_bucket(self):
        bli.create_bucket(bucket_name)

        # part 1: upload
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = pathlib.Path(tmpdir)

            # root files
            _write_prf(tmpdir, ".hidden_file")
            _write_prf(tmpdir, "file1")
            _write_prf(tmpdir, "file2")
            _write_prf(tmpdir, "file3")

            # nested files
            directory = tmpdir.joinpath("directory")
            directory.mkdir()
            _write_prf(directory, ".nested_hidden_file")
            file4 = _write_prf(directory, "file4")

            # hidden directory, should be ignored
            hidden_directory = tmpdir.joinpath(".hidden_directory")
            hidden_directory.mkdir()
            _write_prf(hidden_directory, "ignored_file")

            # tests listing the local files
            self.assertSetEqual(set(bli._yield_local_relative_paths_md5(tmpdir)), result1)

            # tests uploading the files
            bli.upload_files(bucket_name, tmpdir)

            # tests listing the remote files
            self.assertSetEqual(set(bli._yield_remote_relative_paths_md5(bucket_name)), result1)

            # adds, changes, deletes files in the source directory
            _write_prf(directory, "file5")
            _write_prf(tmpdir, "file3", 2000)
            os.remove(file4)

            # tests updating the files
            bli.upload_files(bucket_name, tmpdir)

            # tests listing the updated remote files
            self.assertSetEqual(set(bli._yield_remote_relative_paths_md5(bucket_name)), result2)

        # part 2: download
        with tempfile.TemporaryDirectory() as tmpdir:
            # tests downloading the files in another directory
            bli.download_files(bucket_name, tmpdir)

            # tests listing the local files
            self.assertSetEqual(set(bli._yield_local_relative_paths_md5(tmpdir)), result2)

        # part 3: delete
        bli.delete_files(bucket_name)
        self.assertSetEqual(set(bli._yield_remote_relative_paths_md5(bucket_name)), set())

        bli.delete_bucket(bucket_name)
