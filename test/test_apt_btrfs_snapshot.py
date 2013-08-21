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
        try:
            out += call[1][0]
        except IndexError:
            pass
    return out

class TestMounting(unittest.TestCase):

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

    @mock.patch('apt_btrfs_snapshot.LowLevelCommands.mount')
    @mock.patch('apt_btrfs_snapshot.LowLevelCommands.umount')
    def test_mount_btrfs_root_volume(self, mock_umount, mock_mount):
        mock_mount.return_value = True
        mock_umount.return_value = True
        apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(self.testdir, "data", "fstab"))
        mp = apt_btrfs.mp
        self.assertTrue(mock_mount.called)
        self.assertTrue("apt-btrfs-snapshot-mp-" in mp)
        self.assertTrue(os.path.exists(mp))
        del apt_btrfs
        self.assertTrue(mock_umount.called)
        self.assertFalse(os.path.exists(mp))

    @mock.patch('apt_btrfs_snapshot.LowLevelCommands.mount')
    @mock.patch('apt_btrfs_snapshot.LowLevelCommands.umount')
    def test_mount_btrfs_root_volume_fails(self, mock_umount, mock_mount):
        mock_mount.return_value = False
        mock_umount.return_value = True
        message = "Unable to mount root volume"
        with self.assertRaisesRegexp(Exception, message):
            apt_btrfs = AptBtrfsSnapshot(
                fstab=os.path.join(self.testdir, "data", "fstab"))
        self.assertTrue(mock_mount.called)
        self.assertFalse(mock_umount.called)
    
    def test_parser_older_than_to_datetime(self):
        apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(self.testdir, "data", "fstab"),
            sandbox=self.sandbox)
        t = apt_btrfs._parse_older_than_to_datetime("5d")
        e = datetime.datetime.now() - datetime.timedelta(5)
        # Check that t is within a second of e
        self.assertTrue(e - t < datetime.timedelta(0, 1))
    

# fake low level snapshot
def mock_snapshot_fn(source, dest):
    shutil.copytree(source, dest, symlinks=True)
    return True
mock_snapshot = mock.Mock(side_effect=mock_snapshot_fn)

# fake low level delete
def mock_delete_fn(which):
    shutil.rmtree(which)
    return True
mock_delete = mock.Mock(side_effect=mock_delete_fn)

@mock.patch('apt_btrfs_snapshot.LowLevelCommands.btrfs_delete_snapshot',
    new=mock_delete)
@mock.patch('apt_btrfs_snapshot.LowLevelCommands.btrfs_subvolume_snapshot',
    new=mock_snapshot)
class TestSnapshotting(unittest.TestCase):
    """ A lengthy setUp function copies a model subvolume tree with parent
        links and some package change info. A couple of LowLevelCommand
        functions are overwritten. All that allows test functions to do some
        real work on the model subvolume tree without any risk of messing
        anything up.
    """
    def setUp(self):#, mock_btrfs_subvolume_snapshot, mock_btrfs_delete_snapshot):
        
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
            sandbox=self.sandbox)

    def tearDown(self):
        del self.apt_btrfs
        shutil.rmtree(self.sandbox)
        try: print(self.output)
        except: pass

    def do_and_find_new(self, function, *args, **kwargs):
        old_dirlist = os.listdir(self.sandbox)
        res = function(*args, **kwargs)
        new_dirlist = os.listdir(self.sandbox)
        newdir = None
        for i in new_dirlist:
            if i not in old_dirlist:
                newdir = i
        return res, newdir
    
    def assert_child_parent_linked(self, child, parent):
        # check parent has been fixed in children
        parent_file = os.path.join(self.sandbox, 
            child, PARENT_LINK)
        self.assertEqual(os.readlink(parent_file), 
            os.path.join(PARENT_DOTS, parent))
    
    def load_changes(self, whose):
        changes_file = os.path.join(self.sandbox, whose, CHANGES_FILE)
        self.assertTrue(os.path.exists(changes_file))
        history = pickle.load(open(changes_file, "rb"))
        return history
        
    def test_parser_older_than_to_datetime(self):
        apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(self.testdir, "data", "fstab"),
            sandbox=self.sandbox)
        t = apt_btrfs._parse_older_than_to_datetime("5d")
        e = datetime.datetime.now() - datetime.timedelta(5)
        # Check that t is within a second of e
        self.assertTrue(e - t < datetime.timedelta(0, 1))

    @mock.patch('sys.stdout')
    def test_btrfs_create_snapshot(self, mock_stdout):
        mock_stdout.side_effect = StringIO()
        if os.path.exists('/tmp/apt_last_snapshot'):
            os.remove('/tmp/apt_last_snapshot')
        res, newdir = self.do_and_find_new(self.apt_btrfs.create)
        # check results
        self.assertTrue(res)
        self.assert_child_parent_linked("@", newdir)
        self.assert_child_parent_linked(newdir, 
            SNAP_PREFIX + "2013-08-06_13:26:30")
        
        args = LowLevelCommands.btrfs_subvolume_snapshot.call_args[0]
        self.assertTrue(len(args), 2)
        self.assertTrue(args[0].endswith("@"))
        self.assertTrue(SNAP_PREFIX in args[1])
        
        history = self.load_changes(newdir)
        self.assertEqual(len(history['install']), 10)
        
        # test skipping if recent
        res = self.apt_btrfs.create()
        output = extract_stdout(mock_stdout)
        expected = "A recent snapshot already exists: "
        self.assertTrue(output.startswith(expected))
        
        # test recent but tag -> create anyway
        res, newdir = self.do_and_find_new(self.apt_btrfs.create, "-tag")
        # check results
        self.assertTrue(res)
        self.assertTrue(newdir.endswith("-tag"))
        self.assert_child_parent_linked("@", newdir)
        
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
        self.assert_child_parent_linked(SNAP_PREFIX + "2013-08-01_19:53:16",
            SNAP_PREFIX + "2013-07-26_14:50:53")
        self.assert_child_parent_linked(
            SNAP_PREFIX + "2013-07-31_12:53:16-raring-to-go", 
            SNAP_PREFIX + "2013-07-26_14:50:53")
        # check that the change records have been consolidated
        history = self.load_changes(SNAP_PREFIX + "2013-08-01_19:53:16")
        self.assertEqual(history['install'], [('two', '2')])
        self.assertEqual(history['auto-install'], history['purge'], [])
        self.assertEqual(history['upgrade'], history['remove'], [])      
        history = self.load_changes(
            SNAP_PREFIX + "2013-07-31_12:53:16-raring-to-go")
        self.assertEqual(history['install'], [('one', '1.1'), ('three', '3')])
        self.assertEqual(history['upgrade'], [('zero', '0, 0.1')])
        self.assertEqual(history['auto-install'], [])
        self.assertEqual(history['purge'], history['remove'], [])

    @mock.patch('sys.stdin')
    @mock.patch('sys.stdout')
    def test_btrfs_set_default(self, mock_stdout, mock_stdin):
        mock_stdout.side_effect = StringIO()
        mock_stdin.side_effect = StringIO()
        res, newdir = self.do_and_find_new(self.apt_btrfs.set_default, 
            SNAP_PREFIX + "2013-08-01_19:53:16",
            tag="-tag")
        # check results
        self.assertTrue(res)
        # check for backup's parent and the 
        # record of dpkg changes
        self.assertTrue(newdir.endswith("-tag"))
        
        self.assert_child_parent_linked(newdir, 
            SNAP_PREFIX + "2013-08-06_13:26:30")

        history = self.load_changes(newdir)
        self.assertEqual(len(history['install']), 10)
                   
        self.assertTrue(os.path.exists(os.path.join(self.sandbox, 
            SNAP_PREFIX + "2013-08-01_19:53:16")))
        
        self.assert_child_parent_linked("@",
            SNAP_PREFIX + "2013-08-01_19:53:16")
        
        args = LowLevelCommands.btrfs_subvolume_snapshot.call_args[0]
        self.assertTrue(len(args), 2)
        self.assertTrue(args[1].endswith("@apt-btrfs-staging"))
        self.assertTrue(SNAP_PREFIX + "" in args[0])

    @mock.patch('sys.stdin')
    @mock.patch('sys.stdout')
    def test_btrfs_set_default_tag_prompting(self, mock_stdout, mock_stdin):
        mock_stdout.side_effect = StringIO()
        mock_stdin.side_effect = StringIO()
        mock_stdin.readline.return_value = "tag"
        res, newdir = self.do_and_find_new(self.apt_btrfs.set_default, 
            SNAP_PREFIX + "2013-08-01_19:53:16")
        # check for backup existance (hard) and its tag (easy)
        pos = len(SNAP_PREFIX)
        self.assertEqual(newdir[pos+19:], "-tag")

    @mock.patch('sys.stdout')
    def test_btrfs_set_default_staging_exists(self, mock_stdout):
        mock_stdout.side_effect = StringIO()
        os.mkdir(os.path.join(self.sandbox, "@apt-btrfs-staging"))
        message = "Reserved directory @apt-btrfs-staging exists\n"
        message += "Please remove from btrfs volume root before trying again"
        with self.assertRaisesRegexp(Exception, message):
            res = self.apt_btrfs.set_default(
                SNAP_PREFIX + "2013-08-01_19:53:16", "tag")

    @mock.patch('sys.stdout')
    def test_rollback_one(self, mock_stdout):
        mock_stdout.side_effect = StringIO()
        res, newdir = self.do_and_find_new(self.apt_btrfs.rollback, tag="-tag")
        self.assert_child_parent_linked("@", 
            SNAP_PREFIX + "2013-08-06_13:26:30")
        # check for backup's tag
        pos = len(SNAP_PREFIX)
        self.assertEqual(newdir[pos+19:], "-tag")
    
    @mock.patch('sys.stdout')
    def test_rollback_five(self, mock_stdout):
        mock_stdout.side_effect = StringIO()
        self.apt_btrfs.rollback(5, "-tag")
        self.assert_child_parent_linked("@", 
            SNAP_PREFIX + "2013-07-26_14:50:53")

    @mock.patch('sys.stdout')
    def test_rollback_six(self, mock_stdout):
        mock_stdout.side_effect = StringIO()
        with self.assertRaisesRegexp(Exception, "Can't rollback that far"):
            self.apt_btrfs.rollback(6, "-tag")
        self.assert_child_parent_linked("@", 
            SNAP_PREFIX + "2013-08-06_13:26:30")

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
        self.assert_child_parent_linked(SNAP_PREFIX + "2013-08-01_19:53:16",
            SNAP_PREFIX + "2013-07-31_00:00:04-tag")
        self.assert_child_parent_linked(SNAP_PREFIX + "2013-07-31_12:53:16-tag",
            SNAP_PREFIX + "2013-07-31_00:00:04-tag")

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

    @mock.patch('sys.stdout')
    def test_recent(self, mock_stdout):
        mock_stdout.side_effect = StringIO()
        res = self.apt_btrfs.recent(5, "@")
        self.assertTrue(res)
        output = extract_stdout(mock_stdout)
        expected = """@ and its predecessors. Showing 5 snapshots.

dpkg history for @
- installs (10):
    linux-generic-lts-raring, linux-headers-3.9.0-030900,
    linux-headers-3.9.0-030900-generic, linux-headers-generic-lts-raring,
    linux-image-3.8.0-27-generic, linux-image-3.9.0-030900-generic,
    linux-image-generic-lts-raring, nemo-dropbox, picasa, python-mock
- auto-installs (7):
    lib32asound2, lib32z1, libc6-i386, linux-headers-3.8.0-27,
    linux-headers-3.8.0-27-generic, lynx-cur, python-gpgme

dpkg history for @apt-snapshot-2013-08-06_13:26:30
- No packages operations recorded

dpkg history for @apt-snapshot-2013-08-06_00:29:05
- No packages operations recorded

dpkg history for @apt-snapshot-2013-08-01_19:53:16
- installs (1):
    two
- removes (1):
    one

dpkg history for @apt-snapshot-2013-07-31_00:00:04
- installs (1):
    one
"""
        self.assertEqual(output, expected)
        res = self.apt_btrfs.recent(9, "@apt-snapshot-2013-08-09_21:08:01")
        self.assertTrue(res)
        output = extract_stdout(mock_stdout)
        expected += """@apt-snapshot-2013-08-09_21:08:01 and its predecessors. Showing 9 snapshots.

dpkg history for @apt-snapshot-2013-08-09_21:08:01
- No packages operations recorded

dpkg history for @apt-snapshot-2013-08-09_21:04:37
- No packages operations recorded

dpkg history for @apt-snapshot-2013-08-08_18:44:47
- No packages operations recorded

dpkg history for @apt-snapshot-2013-08-06_13:26:30
- No packages operations recorded

dpkg history for @apt-snapshot-2013-08-06_00:29:05
- No packages operations recorded

dpkg history for @apt-snapshot-2013-08-01_19:53:16
- installs (1):
    two
- removes (1):
    one

dpkg history for @apt-snapshot-2013-07-31_00:00:04
- installs (1):
    one

dpkg history for @apt-snapshot-2013-07-26_14:50:53
- No packages operations recorded
"""
        self.assertEqual(output, expected)

    def test_prune(self):
        message = "Snapshot is not the end of a branch"
        with self.assertRaisesRegexp(Exception, message):
            res = self.apt_btrfs.prune("@apt-snapshot-2013-08-09_21:08:01")
        old_dirlist = os.listdir(self.sandbox)
        
        res = self.apt_btrfs.prune("@apt-snapshot-2013-08-09_21:09:40")
        self.assertTrue(res)
        new_dirlist = os.listdir(self.sandbox)
        self.assertEqual(len(old_dirlist), len(new_dirlist) + 2)
        self.assertNotIn(SNAP_PREFIX + "2013-08-09_21:09:40", new_dirlist)
        self.assertNotIn(SNAP_PREFIX + "2013-08-09_21:08:01", new_dirlist)
        
        res = self.apt_btrfs.prune("@apt-snapshot-2013-08-09_21:05:56")
        self.assertTrue(res)
        new_dirlist = os.listdir(self.sandbox)
        self.assertEqual(len(old_dirlist), len(new_dirlist) + 5)
        self.assertNotIn("@apt-snapshot-2013-08-09_21:05:56", new_dirlist)
        self.assertNotIn("@apt-snapshot-2013-08-09_21:04:37", new_dirlist)
        self.assertNotIn("@apt-snapshot-2013-08-08_18:44:47", new_dirlist)


if __name__ == "__main__":
    unittest.main()
