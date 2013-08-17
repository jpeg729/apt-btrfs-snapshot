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
import datetime
import shutil
import time
import cPickle as pickle
import types

sys.path.insert(0, "..")
sys.path.insert(0, ".")
import snapshots
from apt_btrfs_snapshot import (
    Fstab,
    AptBtrfsSnapshot,
    LowLevelCommands,
    supported, 
)
from snapshots import (
    PARENT_LINK, 
    CHANGES_FILE, 
    SNAP_PREFIX, 
    PARENT_DOTS, 
    Snapshot, 
)


def extract_stdout(mock_stdout, last_line_only=False):
    out = ""
    if last_line_only == True:
        return mock_stdout.method_calls[-2][1][0]
    for call in mock_stdout.method_calls:
        out += call[1][0]
    return out

class TestFstab(unittest.TestCase):

    def setUp(self):
        self.testdir = os.path.dirname(os.path.abspath(__file__))
        # make a copy of a model btrfs subvol tree
        model_root = os.path.join(self.testdir, "data", "model_root")
        self.sandbox = os.path.join(self.testdir, "data", "root3")
        if os.path.exists(self.sandbox):
            shutil.rmtree(self.sandbox)
        shutil.copytree(model_root, self.sandbox, symlinks=True)

    def tearDown(self):
        shutil.rmtree(self.sandbox)

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

    @mock.patch('apt_btrfs_snapshot.LowLevelCommands')
    def test_mount_btrfs_root_volume(self, mock_commands):
        apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(self.testdir, "data", "fstab"))
        mock_commands.mount.return_value = True
        mock_commands.umount.return_value = True
        mp = apt_btrfs.mp
        self.assertTrue(apt_btrfs.commands.mount.called)
        self.assertTrue("apt-btrfs-snapshot-mp-" in mp)
        self.assertTrue(os.path.exists(mp))
        commands = apt_btrfs.commands
        del apt_btrfs
        self.assertTrue(commands.umount.called)
        self.assertFalse(os.path.exists(mp))
    
    def test_parser_older_than_to_datetime(self):
        apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(self.testdir, "data", "fstab"),
            test_mp=self.sandbox)
        t = apt_btrfs._parse_older_than_to_datetime("5d")
        e = datetime.datetime.now() - datetime.timedelta(5)
        # Check that t is within a second of e
        self.assertTrue(e - t < datetime.timedelta(0, 1))
    

class TestSnapshotting(unittest.TestCase):
    """ A lengthy setUp function copies a model subvolume tree with parent
        links and some package change info. A couple of LowLevelCommand
        functions are overwritten. All that allows test functions to do some
        real work on the model subvolume tree without any risk of messing
        anything up.
    """
    def setUp(self):
        self.testdir = os.path.dirname(os.path.abspath(__file__))
        # make a copy of a model btrfs subvol tree
        model_root = os.path.join(self.testdir, "data", "model_root")
        self.sandbox = os.path.join(self.testdir, "data", "root3")
        if os.path.exists(self.sandbox):
            shutil.rmtree(self.sandbox)
        shutil.copytree(model_root, self.sandbox, symlinks=True)
        # setup snapshot class
        self.apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(self.testdir, "data", "fstab"),
            test_mp=self.sandbox)
        # hack to replace low level snapshot command with a working copy func
        # that reports back on its working.
        # I couldn't see how to do this class-wide using mock
        self.new_parent = None
        self.args = []
        def mock_snapshot(source, dest):
            shutil.copytree(source, dest, symlinks=True)
            if source.endswith("@"):
                self.new_parent = os.path.split(dest)
            else:
                self.new_parent = os.path.split(source)
            self.args = source, dest
            return True
        self.apt_btrfs.commands.btrfs_subvolume_snapshot = mock_snapshot
        # low level delete
        def mock_delete(which):
            shutil.rmtree(which)
            return True
        self.apt_btrfs.commands.btrfs_delete_snapshot = mock_delete

    def tearDown(self):
        del self.apt_btrfs
        shutil.rmtree(self.sandbox)
        try: print(self.output)
        except: pass

    @mock.patch('sys.stdout')
    def test_btrfs_create_snapshot(self, mock_stdout):
        mock_stdout.side_effect = StringIO()
        if os.path.exists('/tmp/apt_last_snapshot'):
            os.remove('/tmp/apt_last_snapshot')
        res = self.apt_btrfs.create()
        # check results
        self.assertTrue(res)
        self.assertTrue(os.path.exists(os.path.join(*self.new_parent)))
        parent_file = os.path.join(self.sandbox, "@", PARENT_LINK)
        self.assertEqual(os.readlink(parent_file), 
            "../../%s" % self.new_parent[1])
        self.assertTrue(len(self.args), 2)
        self.assertTrue(self.args[0].endswith("@"))
        self.assertTrue(SNAP_PREFIX + "" in self.args[1])
        changes_file = os.path.join(self.sandbox, self.new_parent[1], 
            CHANGES_FILE)
        self.assertTrue(os.path.exists(changes_file))
        history = pickle.load(open(changes_file, "rb"))
        self.assertEqual(len(history['install']), 10)
        # test skipping if recent
        res = self.apt_btrfs.create()
        output = extract_stdout(mock_stdout)
        expected = "A recent snapshot already exists: "
        self.assertTrue(output.startswith(expected))
        # test disabling by shell variable
        os.environ['APT_NO_SNAPSHOTS'] = '1'
        res = self.apt_btrfs.create()
        output = extract_stdout(mock_stdout, last_line_only=True)
        expected = "Shell variable APT_NO_SNAPSHOTS found, skipping creation"
        self.assertTrue(output.startswith(expected))
        # shell var AND tag supplied -> create anyway
        res = self.apt_btrfs.create("tag")
        output = extract_stdout(mock_stdout, last_line_only=True)
        expected = "Shell variable APT_NO_SNAPSHOTS found, but tag supplied, "
        expected += "creating snapshot"
        self.assertTrue(output.startswith(expected))
        del os.environ['APT_NO_SNAPSHOTS']

    def test_btrfs_delete_snapshot(self):
        which = SNAP_PREFIX + "2013-07-31_00:00:04"
        res = self.apt_btrfs.delete(which)
        self.assertTrue(res)
        self.assertFalse(os.path.exists(os.path.join(self.sandbox, which)))
        # check parent has been fixed in children
        parent_file = os.path.join(self.sandbox, 
            SNAP_PREFIX + "2013-08-01_19:53:16", PARENT_LINK)
        self.assertEqual(os.readlink(parent_file), 
            os.path.join(PARENT_DOTS, SNAP_PREFIX + "2013-07-26_14:50:53"))
        parent_file = os.path.join(self.sandbox, 
            SNAP_PREFIX + "2013-07-31_12:53:16-raring-to-go", PARENT_LINK)
        self.assertEqual(os.readlink(parent_file), 
            os.path.join(PARENT_DOTS, SNAP_PREFIX + "2013-07-26_14:50:53"))
        # check that the change records have been consolidated
        changes_file = os.path.join(self.sandbox, 
            SNAP_PREFIX + "2013-08-01_19:53:16", CHANGES_FILE)
        history = pickle.load(open(changes_file, "rb"))
        self.assertEqual(history['install'], [('two', '2')])
        self.assertEqual(history['auto-install'], history['purge'], [])
        self.assertEqual(history['upgrade'], history['remove'], [])      
        changes_file = os.path.join(self.sandbox, 
            SNAP_PREFIX + "2013-07-31_12:53:16-raring-to-go", CHANGES_FILE)
        history = pickle.load(open(changes_file, "rb"))
        self.assertEqual(history['install'], [('one', '1.1'), ('three', '3')])
        self.assertEqual(history['upgrade'], [('zero', '0, 0.1')])
        self.assertEqual(history['auto-install'], [])
        self.assertEqual(history['purge'], history['remove'], [])

    @mock.patch('sys.stdin')
    @mock.patch('sys.stdout')
    def test_btrfs_set_default(self, mock_stdout, mock_stdin):
        mock_stdout.side_effect = StringIO()
        mock_stdin.side_effect = StringIO()
        old_listdir = os.listdir(self.sandbox)
        res = self.apt_btrfs.set_default(SNAP_PREFIX + "2013-08-01_19:53:16", 
            tag="-tag")
        # check results
        self.assertTrue(res)
        # check for backup existance (hard) and its parent (easy) and the 
        # record of dpkg changes
        new_listdir = os.listdir(self.sandbox)
        for i in new_listdir:
            if i not in old_listdir:
                parent_file = os.path.join(self.sandbox, i, PARENT_LINK)
                self.assertEqual(os.readlink(parent_file), 
                    os.path.join(PARENT_DOTS, SNAP_PREFIX + "2013-08-06_13:26:30"))
                changes_file = os.path.join(self.sandbox, i, CHANGES_FILE)
                self.assertTrue(os.path.exists(changes_file))
                history = pickle.load(open(changes_file, "rb"))
                self.assertEqual(len(history['install']), 10)
                   
        self.assertTrue(os.path.exists(os.path.join(self.sandbox, 
            SNAP_PREFIX + "2013-08-01_19:53:16")))
        parent_file = os.path.join(self.sandbox, "@", PARENT_LINK)
        self.assertEqual(os.readlink(parent_file), 
            os.path.join(PARENT_DOTS, SNAP_PREFIX + "2013-08-01_19:53:16"))
        self.assertTrue(len(self.args), 2)
        self.assertTrue(self.args[1].endswith("@apt-btrfs-staging"))
        self.assertTrue(SNAP_PREFIX + "" in self.args[0])

    @mock.patch('sys.stdin')
    @mock.patch('sys.stdout')
    def test_btrfs_set_default_tag_prompting(self, mock_stdout, mock_stdin):
        mock_stdout.side_effect = StringIO()
        mock_stdin.side_effect = StringIO()
        mock_stdin.readline.return_value = "tag"
        old_listdir = os.listdir(self.sandbox)
        res = self.apt_btrfs.set_default(SNAP_PREFIX + "2013-08-01_19:53:16")
        # check for backup existance (hard) and its tag (easy)
        new_listdir = os.listdir(self.sandbox)
        for i in new_listdir:
            if i not in old_listdir:
                pos = len(SNAP_PREFIX)
                self.assertEqual(i[pos+19:], "-tag")

    @mock.patch('sys.stdout')
    def test_btrfs_set_default_tag_prompting(self, mock_stdout):
        mock_stdout.side_effect = StringIO()
        os.mkdir(os.path.join(self.sandbox, "@apt-btrfs-staging"))
        message = "Reserved directory @apt-btrfs-staging exists\n"
        message += "Please remove from btrfs volume root before trying again"
        with self.assertRaisesRegexp(Exception, message):
            res = self.apt_btrfs.set_default(SNAP_PREFIX + \
                "2013-08-01_19:53:16", "tag")

    @mock.patch('sys.stdout')
    def test_rollback_one(self, mock_stdout):
        mock_stdout.side_effect = StringIO()
        old_listdir = os.listdir(self.sandbox)
        self.apt_btrfs.rollback(tag="-tag")
        parent_file = os.path.join(self.sandbox, "@", PARENT_LINK)
        self.assertEqual(os.readlink(parent_file), 
            os.path.join(PARENT_DOTS, SNAP_PREFIX + "2013-08-06_13:26:30"))
        # check for backup existance (hard) and its tag (easy)
        new_listdir = os.listdir(self.sandbox)
        for i in new_listdir:
            if i not in old_listdir:
                pos = len(SNAP_PREFIX)
                self.assertEqual(i[pos+19:], "-tag")
    
    @mock.patch('sys.stdout')
    def test_rollback_five(self, mock_stdout):
        mock_stdout.side_effect = StringIO()
        self.apt_btrfs.rollback(5, "-tag")
        parent_file = os.path.join(self.sandbox, "@", PARENT_LINK)
        self.assertEqual(os.readlink(parent_file), 
            os.path.join(PARENT_DOTS, SNAP_PREFIX + "2013-07-26_14:50:53"))

    @mock.patch('sys.stdout')
    def test_rollback_six(self, mock_stdout):
        mock_stdout.side_effect = StringIO()
        with self.assertRaisesRegexp(Exception, "Can't rollback that far"):
            self.apt_btrfs.rollback(6, "-tag")
        parent_file = os.path.join(self.sandbox, "@", PARENT_LINK)
        self.assertEqual(os.readlink(parent_file), 
            os.path.join(PARENT_DOTS, SNAP_PREFIX + "2013-08-06_13:26:30"))

    def test_get_status(self):
        date, history = self.apt_btrfs._get_status()
        self.assertEqual(len(history['install']), 10)
        self.assertEqual(len(history['auto-install']), 7)
        self.assertEqual(history['remove'], history['purge'], [])
        self.assertEqual(history['upgrade'], [])     
    
    @mock.patch('sys.stdout')
    def test_tree_view(self, mock_stdout): 
        mock_stdout.side_effect = StringIO()
        self.maxDiff = None
        self.apt_btrfs.tree()
        output = extract_stdout(mock_stdout)
        expected = """@ (+17)
│  
│  @apt-snapshot-2013-08-09_21:09:40 (unknown)
│  @apt-snapshot-2013-08-09_21:08:01 (unknown)
│  │  
│  │  @apt-snapshot-2013-08-09_21:06:32 (unknown)
│  │  ×  
│  │     @apt-snapshot-2013-08-09_21:05:56 (unknown)
│  ├─────┘
│  @apt-snapshot-2013-08-09_21:04:37 (unknown)
│  @apt-snapshot-2013-08-08_18:44:47 (unknown)
├──┘
@apt-snapshot-2013-08-06_13:26:30 (unknown)
@apt-snapshot-2013-08-06_00:29:05 (unknown)
│  
│  @apt-snapshot-2013-08-09_21:06:00 (unknown)
│  │  
│  │  @apt-snapshot-2013-08-07_18:00:42 (unknown)
│  │  ×  
│  │     @apt-snapshot-2013-08-05_04:30:58 (unknown)
│  ├─────┘
│  @apt-snapshot-2013-08-02_00:24:00 (unknown)
├──┘
@apt-snapshot-2013-08-01_19:53:16 (+1 -1)
│  
│  @apt-snapshot-2013-07-31_12:53:16-raring-to-go (+1 ^2)
├──┘
@apt-snapshot-2013-07-31_00:00:04 (+1)
@apt-snapshot-2013-07-26_14:50:53 (unknown)
×  
"""
        self.assertEqual(output, expected)
        
        Snapshot(SNAP_PREFIX + "2013-08-09_21:06:00").parent = None
        # reinitialize snapshots global variables.
        snapshots.setup(self.sandbox)
        self.apt_btrfs.tree()
        output = extract_stdout(mock_stdout)
        expected += """@ (+17)
│  
│  @apt-snapshot-2013-08-09_21:09:40 (unknown)
│  @apt-snapshot-2013-08-09_21:08:01 (unknown)
│  │  
│  │  @apt-snapshot-2013-08-09_21:06:32 (unknown)
│  │  ×  
│  │     @apt-snapshot-2013-08-09_21:06:00 (unknown)
│  │     ×  
│  │        @apt-snapshot-2013-08-09_21:05:56 (unknown)
│  ├────────┘
│  @apt-snapshot-2013-08-09_21:04:37 (unknown)
│  @apt-snapshot-2013-08-08_18:44:47 (unknown)
├──┘
@apt-snapshot-2013-08-06_13:26:30 (unknown)
@apt-snapshot-2013-08-06_00:29:05 (unknown)
│  
│  @apt-snapshot-2013-08-07_18:00:42 (unknown)
│  ×  
│     @apt-snapshot-2013-08-05_04:30:58 (unknown)
│     @apt-snapshot-2013-08-02_00:24:00 (unknown)
├─────┘
@apt-snapshot-2013-08-01_19:53:16 (+1 -1)
│  
│  @apt-snapshot-2013-07-31_12:53:16-raring-to-go (+1 ^2)
├──┘
@apt-snapshot-2013-07-31_00:00:04 (+1)
@apt-snapshot-2013-07-26_14:50:53 (unknown)
×  
"""
        self.assertEqual(output, expected)

    def test_tag(self):
        self.apt_btrfs.tag(SNAP_PREFIX + "2013-07-31_00:00:04", "-tag")
        dirlist = os.listdir(self.sandbox)
        self.assertIn(SNAP_PREFIX + "2013-07-31_00:00:04-tag", dirlist)
        self.assertNotIn(SNAP_PREFIX + "2013-07-31_00:00:04", dirlist)
        
        self.apt_btrfs.tag(SNAP_PREFIX + "2013-07-31_12:53:16-raring-to-go",
            "-tag")
        dirlist = os.listdir(self.sandbox)
        self.assertIn(SNAP_PREFIX + "2013-07-31_12:53:16-tag", dirlist)
        self.assertNotIn(SNAP_PREFIX + "2013-07-31_12:53:16-raring-to-go",
            dirlist)
        # check parent has been fixed in children
        parent_file = os.path.join(self.sandbox, 
            SNAP_PREFIX + "2013-08-01_19:53:16", PARENT_LINK)
        self.assertEqual(os.readlink(parent_file), 
            os.path.join(PARENT_DOTS, SNAP_PREFIX + "2013-07-31_00:00:04-tag"))
        parent_file = os.path.join(self.sandbox, 
            SNAP_PREFIX + "2013-07-31_12:53:16-tag", PARENT_LINK)
        self.assertEqual(os.readlink(parent_file), 
            os.path.join(PARENT_DOTS, SNAP_PREFIX + "2013-07-31_00:00:04-tag"))

    def test_clean_apt_cache(self):
        self.apt_btrfs.clean()
        path = os.path.join(self.sandbox, "@/var/cache/apt/archives")
        self.assertTrue(os.path.exists(os.path.join(path, "a.deb")))
        path = os.path.join(self.sandbox, 
            SNAP_PREFIX + "2013-08-07_18:00:42", "var/cache/apt/archives")
        self.assertFalse(os.path.exists(os.path.join(path, "a.deb")))
        self.assertFalse(os.path.exists(os.path.join(path, "b.deb")))
        self.assertTrue(os.path.exists(os.path.join(path, "other_file")))

    def test_delete_older_than(self):
        old_dirlist = os.listdir(self.sandbox)
        self.apt_btrfs.delete_older_than(
            datetime.datetime(2013, 8, 7, 18, 0, 42))
        dirlist = os.listdir(self.sandbox)
        self.assertEqual(len(dirlist), len(old_dirlist) - 4)
        self.assertNotIn(SNAP_PREFIX + "2013-07-26_14:50:53", dirlist)
        self.assertNotIn(SNAP_PREFIX + "2013-08-06_00:29:05", dirlist)
        self.assertNotIn(SNAP_PREFIX + "2013-08-05_04:30:58", dirlist)
        self.assertNotIn(SNAP_PREFIX + "2013-08-02_00:24:00", dirlist)
        
        old_dirlist = os.listdir(self.sandbox)
        self.apt_btrfs.delete_older_than(
            datetime.datetime(2013, 8, 9, 21, 9, 40))
        dirlist = os.listdir(self.sandbox)
        self.assertEqual(len(dirlist), len(old_dirlist) - 8)
        self.assertNotIn(SNAP_PREFIX + "2013-08-09_21:08:01", dirlist)
        self.assertNotIn(SNAP_PREFIX + "2013-08-09_21:06:32", dirlist)
        self.assertNotIn(SNAP_PREFIX + "2013-08-09_21:06:00", dirlist)
        self.assertNotIn(SNAP_PREFIX + "2013-08-09_21:05:56", dirlist)
        
        self.assertNotIn(SNAP_PREFIX + "2013-08-09_21:04:37", dirlist)
        self.assertNotIn(SNAP_PREFIX + "2013-08-08_18:44:47", dirlist)
        self.assertNotIn(SNAP_PREFIX + "2013-08-07_18:00:42", dirlist)
        self.assertNotIn(SNAP_PREFIX + "2013-08-01_19:53:16", dirlist)


if __name__ == "__main__":
    unittest.main()
