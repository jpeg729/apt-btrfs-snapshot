#!/usr/bin/python

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
import pickle
import types

sys.path.insert(0, "..")
sys.path.insert(0, ".")
from apt_btrfs_snapshot import (
    Fstab,
    AptBtrfsSnapshot,
    LowLevelCommands,
    supported, 
)


def debug(*args):
    print(*args)
    return True


class TestFstab(unittest.TestCase):

    def setUp(self):
        self.testdir = os.path.dirname(os.path.abspath(__file__))
        # make a copy of a model btrfs subvol tree
        model_root = os.path.join(self.testdir, "data", "model_root")
        self.model_root = os.path.join(self.testdir, "data", "root3")
        if os.path.exists(self.model_root):
            shutil.rmtree(self.model_root)
        shutil.copytree(model_root, self.model_root, symlinks=True)

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
            fstab=os.path.join(self.testdir, "data", "fstab"),
            test_mp=self.model_root)
        mock_commands.mount.return_value = True
        mock_commands.umount.return_value = True
        mp = apt_btrfs.mount_btrfs_root_volume()
        self.assertTrue(apt_btrfs.commands.mount.called)
        self.assertTrue("apt-btrfs-snapshot-mp-" in mp)
        self.assertTrue(apt_btrfs.umount_btrfs_root_volume())
        self.assertTrue(apt_btrfs.commands.umount.called)
        self.assertFalse(os.path.exists(mp))

    def test_parser_older_than_to_datetime(self):
        apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(self.testdir, "data", "fstab"),
            test_mp=self.model_root)
        t = apt_btrfs._parse_older_than_to_datetime("5d")
        e = datetime.datetime.now() - datetime.timedelta(5)
        # Check that t is within a second of e
        self.assertTrue(e - t < datetime.timedelta(0, 1))
    
    def test_list_snapshots(self):
        apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(self.testdir, "data", "fstab"),
            test_mp=os.path.join(self.testdir, "data", "root"))
        self.mp = os.path.join(
                               self.testdir, "data", "root")
        res = apt_btrfs.get_btrfs_root_snapshots_list()
        dirlist = os.listdir(os.path.join(self.testdir, "data", "root"))
        dirlist = [i for i in dirlist if i.startswith("@apt-snapshot")]
        self.assertEqual(len(res), len(dirlist))
        for i in dirlist:
            self.assertIn(i, res)

    def test_list_snapshots(self):
        apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(self.testdir, "data", "fstab"),
            test_mp=os.path.join(self.testdir, "data", "root"))
        self.mp = os.path.join(
                               self.testdir, "data", "root")
        older_than = datetime.datetime(2013, 8, 3)
        res = apt_btrfs.get_btrfs_root_snapshots_list(older_than=older_than)
        self.assertEqual(len(res), 10)
        
        older_than = datetime.datetime(2013, 7, 27)
        res = apt_btrfs.get_btrfs_root_snapshots_list(older_than=older_than)
        self.assertEqual(len(res), 4)
        
        res = apt_btrfs.get_btrfs_root_snapshots_list()
        self.assertEqual(len(res), 26)


class TestSnapshotting(unittest.TestCase):

    def setUp(self):
        self.testdir = os.path.dirname(os.path.abspath(__file__))
        # make a copy of a model btrfs subvol tree
        model_root = os.path.join(self.testdir, "data", "model_root")
        self.model_root = os.path.join(self.testdir, "data", "root3")
        if os.path.exists(self.model_root):
            shutil.rmtree(self.model_root)
        shutil.copytree(model_root, self.model_root, symlinks=True)
        # setup snapshot class
        self.apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(self.testdir, "data", "fstab"),
            test_mp=self.model_root)
        # hack to replace low level snapshot command with a working copy func
        # that reports back on its working
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
        shutil.rmtree(self.model_root)

    def test_get_children(self):
        res = self.apt_btrfs._get_children("@apt-snapshot-2013-07-31_00:00:04")
        self.assertEqual(len(res), 2)
        self.assertIn("@apt-snapshot-2013-08-01_19:53:16", res)
        self.assertIn("@apt-snapshot-2013-07-31_12:53:16-raring-to-go", res)
        self.assertEqual(res, 
            self.apt_btrfs.children["@apt-snapshot-2013-07-31_00:00:04"])

    def test_get_parent(self):
        res = self.apt_btrfs._get_parent("@apt-snapshot-2013-07-31_00:00:04")
        self.assertEqual(res, "@apt-snapshot-2013-07-26_14:50:53", 
            self.apt_btrfs.parents["@apt-snapshot-2013-07-31_00:00:04"])
        self.assertIn("@", self.apt_btrfs.parents.keys())

    def test_btrfs_create_snapshot(self):
        res = self.apt_btrfs.snapshot()
        # check results
        self.assertTrue(res)
        self.assertTrue(os.path.exists(os.path.join(*self.new_parent)))
        parent_file = os.path.join(self.model_root, "@", "etc", 
            "apt-btrfs-parent")
        self.assertEqual(os.readlink(parent_file), 
            "../../%s" % self.new_parent[1])
        self.assertTrue(len(self.args), 2)
        self.assertTrue(self.args[0].endswith("@"))
        self.assertTrue("@apt-snapshot-" in self.args[1])
        changes_file = os.path.join(self.model_root, self.new_parent[1], "etc", 
            "apt-btrfs-changes")
        self.assertTrue(os.path.exists(changes_file))
        history = pickle.load(open(changes_file, "rb"))
        self.assertEqual(len(history['install']), 10)

    @mock.patch('sys.stdout')
    def test_btrfs_set_default(self, mock_stdout):
        mock_stdout.side_effect = StringIO()
        old_listdir = os.listdir(self.model_root)
        res = self.apt_btrfs.set_default("@apt-snapshot-2013-08-01_19:53:16")
        # check results
        self.assertTrue(res)
        # check for backup existance (hard) and its parent (easy)
        new_listdir = os.listdir(self.model_root)
        for i in new_listdir:
            if not i in old_listdir:
                parent_file = os.path.join(self.model_root, i, "etc", 
                    "apt-btrfs-parent")
                self.assertEqual(os.readlink(parent_file), 
                    "../../@apt-snapshot-2013-08-06_13:26:30")
                changes_file = os.path.join(self.model_root, i, "etc", 
                    "apt-btrfs-changes")
                self.assertTrue(os.path.exists(changes_file))
                history = pickle.load(open(changes_file, "rb"))
                self.assertEqual(len(history['install']), 10)
                   
        self.assertTrue(os.path.exists(os.path.join(self.model_root, 
            "@apt-snapshot-2013-08-01_19:53:16")))
        parent_file = os.path.join(self.model_root, "@", "etc", 
            "apt-btrfs-parent")
        self.assertEqual(os.readlink(parent_file), 
            "../../@apt-snapshot-2013-08-01_19:53:16")
        self.assertTrue(len(self.args), 2)
        self.assertTrue(self.args[1].endswith("@apt-btrfs-staging"))
        self.assertTrue("@apt-snapshot-" in self.args[0])

    def test_btrfs_delete_snapshot(self):
        which = "@apt-snapshot-2013-07-31_00:00:04"
        res = self.apt_btrfs.delete(which)
        self.assertTrue(res)
        self.assertFalse(os.path.exists(os.path.join(self.model_root, 
            which)))
        # check parent has been fixed in children
        parent_file = os.path.join(self.model_root, 
            "@apt-snapshot-2013-08-01_19:53:16", "etc", "apt-btrfs-parent")
        self.assertEqual(os.readlink(parent_file), 
            "../../@apt-snapshot-2013-07-26_14:50:53")
        parent_file = os.path.join(self.model_root, 
            "@apt-snapshot-2013-07-31_12:53:16-raring-to-go", 
            "etc", "apt-btrfs-parent")
        self.assertEqual(os.readlink(parent_file), 
            "../../@apt-snapshot-2013-07-26_14:50:53")

    def test_link(self):
        child = "@apt-snapshot-2013-07-31_12:53:16-raring-to-go"
        self.apt_btrfs._link(None, child)
        parent_file = os.path.join(self.model_root, 
            "@apt-snapshot-2013-07-31_12:53:16-raring-to-go", 
            "etc", "apt-btrfs-parent")
        self.assertFalse(os.path.exists(parent_file))
        self.apt_btrfs._link("@apt-snapshot-2013-07-26_14:50:53", child)
        self.assertEqual(os.readlink(parent_file), 
            "../../@apt-snapshot-2013-07-26_14:50:53")

    @mock.patch('sys.stdout')
    def test_rollback_one(self, mock_stdout):
        mock_stdout.side_effect = StringIO()
        self.apt_btrfs.rollback()
        parent_file = os.path.join(self.model_root, 
            "@", "etc", "apt-btrfs-parent")
        self.assertEqual(os.readlink(parent_file), 
            "../../@apt-snapshot-2013-08-06_13:26:30")
    # if desired these two tests can be put in the same function, but you will
    # incur a 1s delay designed to avoid trying to create two snapshots of the 
    # same name
    @mock.patch('sys.stdout')
    def test_rollback_five(self, mock_stdout):
        mock_stdout.side_effect = StringIO()
        self.apt_btrfs.rollback(5)
        parent_file = os.path.join(self.model_root, 
            "@", "etc", "apt-btrfs-parent")
        self.assertEqual(os.readlink(parent_file), 
            "../../@apt-snapshot-2013-08-01_19:53:16")

    def test_get_status(self):
        date, history = self.apt_btrfs._get_status()
        self.assertEqual(len(history['install']), 10)
        self.assertEqual(len(history['auto-install']), 7)
        self.assertEqual(len(history['remove']), 
            len(history['purge']), 0)
        self.assertEqual(len(history['upgrade']), 0)      


if __name__ == "__main__":
    unittest.main()
