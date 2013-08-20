#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import print_function, unicode_literals

try:
    from StringIO import StringIO
    StringIO  # pyflakes
except ImportError:
    from io import StringIO
import os
import sys
import unittest
import subprocess
import shutil
import mock

sys.path.insert(0, "..")
sys.path.insert(0, ".")
import snapshots
from snapshots import (
    Snapshot,
    PARENT_LINK, 
    CHANGES_FILE, 
    SNAP_PREFIX, 
    PARENT_DOTS, 
)
from apt_btrfs_snapshot import AptBtrfsSnapshot


def extract_stdout(mock_stdout, last_line_only=False):
    out = ""
    if last_line_only == True:
        return mock_stdout.method_calls[-2][1][0]
    for call in mock_stdout.method_calls:
        tup = call[1]
        if len(tup):
            out += tup[0]
    return out
    
    
class TestSnapshot(unittest.TestCase):

    def setUp(self):
        self.testdir = os.path.dirname(os.path.abspath(__file__))
        # make a copy of a model btrfs subvol tree
        model_root = os.path.join(self.testdir, "data", "model_to_convert")
        self.sandbox = os.path.join(self.testdir, "data", "root3")
        if os.path.exists(self.sandbox):
            shutil.rmtree(self.sandbox)
        shutil.copytree(model_root, self.sandbox, symlinks=True)
        snapshots.setup(self.sandbox)

    def tearDown(self):
        shutil.rmtree(self.sandbox)
        try: print(self.output)
        except: pass

    @mock.patch('sys.stdout')
    def test_convert(self, mock_stdout):
        mock_stdout.side_effect = StringIO()
        subprocess.call(["python", "../convert.py", self.sandbox])
        apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(self.testdir, "data", "fstab"),
            test_mp=self.sandbox)
        apt_btrfs.tree()
        output = extract_stdout(mock_stdout)
        expected = u"""@ (none)
@apt-snapshot-2013-08-15_23:04:32 (+1)
@apt-snapshot-2013-08-14_20:26:45 (^13)
@apt-snapshot-2013-08-13_12:23:41 (+8)
@apt-snapshot-2013-08-13_03:11:29 (+6 ^3)
@apt-snapshot-2013-08-12_02:04:06 (unknown)
×  
"""
        self.assertEqual(output, expected)
        snapshots.setup(self.sandbox)
        # The following change information tests have been meticulously 
        # verified.
        changes = Snapshot("@apt-snapshot-2013-08-15_23:04:32").changes
        self.assertEqual(changes['install'], [(u'handbrake-gtk',
            u'5698svnppa1~precise1')])
        self.assertEqual(changes['auto-install'], [])
        self.assertEqual(changes['upgrade'], [])
        self.assertEqual(changes['remove'], [])
        self.assertEqual(changes['purge'], [])
        changes = Snapshot("@apt-snapshot-2013-08-14_20:26:45").changes
        self.assertEqual(changes['install'], [])
        self.assertEqual(changes['auto-install'], [])
        self.assertEqual(changes['upgrade'], [(u'firefox', u'22.0+build2-0ubuntu0.12.04.2, 23.0+build2-0ubuntu0.12.04.1'), (u'firefox-locale-en', u'22.0+build2-0ubuntu0.12.04.2, 23.0+build2-0ubuntu0.12.04.1'), (u'gimp-help-common', u'2.6.1-1, 1:2.8-0precise16~ppa'), (u'gimp-help-en', u'2.6.1-1, 1:2.8-0precise16~ppa'), (u'gimp-help-fr', u'2.6.1-1, 1:2.8-0precise16~ppa'), (u'jockey-common', u'0.9.7-0ubuntu7.7, 0.9.7-0ubuntu7.9'), (u'jockey-gtk', u'0.9.7-0ubuntu7.7, 0.9.7-0ubuntu7.9'), (u'lsb-base', u'4.0-0ubuntu20.2, 4.0-0ubuntu20.3'), (u'lsb-release', u'4.0-0ubuntu20.2, 4.0-0ubuntu20.3'), (u'mintinstall-icons', u'1.0.5, 1.0.7'), (u'python-problem-report', u'2.0.1-0ubuntu17.3, 2.0.1-0ubuntu17.4'), (u'thunderbird', u'17.0.7+build1-0ubuntu0.12.04.1, 17.0.8+build1-0ubuntu0.12.04.1'), (u'thunderbird-gnome-support', u'17.0.7+build1-0ubuntu0.12.04.1, 17.0.8+build1-0ubuntu0.12.04.1')])
        self.assertEqual(changes['remove'], [])
        self.assertEqual(changes['purge'], [])
        changes = Snapshot("@apt-snapshot-2013-08-13_12:23:41").changes
        self.assertEqual(changes['install'], [(u'0ad', u'0.0.13-0ubuntu1~12.04~wfg1')])
        self.assertEqual(changes['auto-install'], [(u'0ad-data', u'0.0.13-0ubuntu1~12.04~wfg1'), (u'0ad-data-common', u'0.0.13-0ubuntu1~12.04~wfg1'), (u'libboost-filesystem1.46.1', u'1.46.1-7ubuntu3'), (u'libboost-signals1.46.1', u'1.46.1-7ubuntu3'), (u'libboost-system1.46.1', u'1.46.1-7ubuntu3'), (u'libenet1a', u'1.3.3-2ubuntu1'), (u'libnvtt2', u'2.0.8-1+dfsg-2')])
        self.assertEqual(changes['upgrade'], [])
        self.assertEqual(changes['remove'], [])
        self.assertEqual(changes['purge'], [])
        changes = Snapshot("@apt-snapshot-2013-08-13_03:11:29").changes
        self.assertEqual(changes['install'], [])
        self.assertEqual(changes['auto-install'], [(u'libamd2.2.0', u'1:3.4.0-2ubuntu3'), (u'libbabl-0.1-0', u'0.1.11-1precise0~ppa'), (u'libblas3gf', u'1.2.20110419-2ubuntu1'), (u'libgegl-0.2-0', u'0.2.1-1precise0~ppa'), (u'libopenraw1', u'0.0.8-3build1'), (u'libumfpack5.4.0', u'1:3.4.0-2ubuntu3')])
        self.assertEqual(changes['upgrade'], [(u'gimp', u'2.6.12-1ubuntu1.2, 2.8.6-0precise1~ppa'), (u'gimp-data', u'2.6.12-1ubuntu1.2, 2.8.6-0precise1~ppa'), (u'libgimp2.0', u'2.6.12-1ubuntu1.2, 2.8.6-0precise1~ppa')])
        self.assertEqual(changes['remove'], [])
        self.assertEqual(changes['purge'], [])
        changes = Snapshot("@apt-snapshot-2013-08-12_02:04:06").changes
        self.assertEqual(changes, None)


if __name__ == "__main__":
    unittest.main()
