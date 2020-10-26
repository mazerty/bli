#!/usr/bin/python3 -u

import unittest

import bli

bucket_name = "test.mazerty.fr"


class TestCase(unittest.TestCase):
    def test_bucket(self):
        bli.create_bucket(bucket_name)
        bli.check_bucket(bucket_name)
        bli.delete_bucket(bucket_name)


unittest.main(verbosity=2)
