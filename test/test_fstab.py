#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import print_function, unicode_literals

try:
    from StringIO import StringIO
    StringIO  # pyflakes
except ImportError:
    from io import StringIO
import mock
import os
import sys
import unittest

sys.path.insert(0, "..")
sys.path.insert(0, ".")
from fstab import (
    Fstab,
)
from apt_btrfs_snapshot import (
    supported,
)

class TestFstab(unittest.TestCase):

    def setUp(self):
        self.testdir = os.path.dirname(os.path.abspath(__file__))

    @mock.patch('os.path.exists')
    def test_fstab_detect_snapshot(self, mock_commands):
        #Using python-mock 0.7 style, for precise compatibility
        mock_commands.side_effect = lambda f: f in ('/sbin/btrf')
        self.assertFalse(supported(
            fstab=os.path.join(self.testdir, "data", "fstab")))
        mock_commands.side_effect = lambda f: f in ('/sbin/btrfs')
        self.assertTrue(supported(
            fstab=os.path.join(self.testdir, "data", "fstab")))
        self.assertFalse(supported(
            fstab=os.path.join(self.testdir, "data", "fstab.no-btrfs")))
        self.assertFalse(supported(
            fstab=os.path.join(self.testdir, "data", "fstab.bug806065")))
        self.assertTrue(supported(
            fstab=os.path.join(self.testdir, "data", "fstab.bug872145")))

    def test_fstab_get_uuid(self):
        fstab = Fstab(
            fstab=os.path.join(self.testdir, "data", "fstab"))
        self.assertEqual(fstab.uuid_for_mountpoint("/"),
                         "UUID=fe63f598-1906-478e-acc7-f74740e78d1f")

if __name__ == "__main__":
    unittest.main()
