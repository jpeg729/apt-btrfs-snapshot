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
from time import sleep
#import testfixtures

sys.path.insert(0, "..")
sys.path.insert(0, ".")
from apt_btrfs_snapshot import (
    AptBtrfsSnapshot,
    LowLevelCommands,
)
import types


def debug(*args):
    print(*args)
    return True


class TestFstab(unittest.TestCase):

    def setUp(self):
        self.testdir = os.path.dirname(os.path.abspath(__file__))

    @mock.patch('os.path.exists')
    def test_fstab_detect_snapshot(self, mock_commands):
        #Using python-mock 0.7 style, for precise compatibility
        mock_commands.side_effect = lambda f: f in ('/sbin/btrfs')
        apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(self.testdir, "data", "fstab"))
        self.assertTrue(apt_btrfs.snapshots_supported())
        apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(self.testdir, "data", "fstab.no-btrfs"))
        self.assertFalse(apt_btrfs.snapshots_supported())
        apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(self.testdir, "data", "fstab.bug806065"))
        self.assertFalse(apt_btrfs.snapshots_supported())
        apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(self.testdir, "data", "fstab.bug872145"))
        self.assertTrue(apt_btrfs.snapshots_supported())

    def test_fstab_get_uuid(self):
        apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(self.testdir, "data", "fstab"))
        self.assertEqual(apt_btrfs._uuid_for_mountpoint("/"),
                         "UUID=fe63f598-1906-478e-acc7-f74740e78d1f")

    @mock.patch('apt_btrfs_snapshot.LowLevelCommands')
    def test_mount_btrfs_root_volume(self, mock_commands):
        apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(self.testdir, "data", "fstab"))
        mock_commands.mount.return_value = True
        mock_commands.umount.return_value = True
        mp = apt_btrfs.mount_btrfs_root_volume()
        self.assertTrue(apt_btrfs.commands.mount.called)
        self.assertTrue("apt-btrfs-snapshot-mp-" in mp)
        self.assertTrue(apt_btrfs.umount_btrfs_root_volume())
        self.assertTrue(apt_btrfs.commands.umount.called)
        self.assertFalse(os.path.exists(mp))

    @mock.patch('apt_btrfs_snapshot.LowLevelCommands')
    @mock.patch('apt_btrfs_snapshot.AptBtrfsSnapshot.mount_btrfs_root_volume')
    @mock.patch('apt_btrfs_snapshot.AptBtrfsSnapshot.umount_btrfs_root_volume')
    def test_btrfs_create_snapshot(self, mock_umount, mock_mount, 
            mock_commands):
        # make a copy of a model btrfs subvol tree
        model_root = os.path.join(self.testdir, "data", "model_root")
        copy_of_model_root = os.path.join(self.testdir, "data", "root3")
        if os.path.exists(copy_of_model_root):
            shutil.rmtree(copy_of_model_root)
        shutil.copytree(model_root, copy_of_model_root, symlinks=True)
        # setup mock
        mock_mount.return_value = copy_of_model_root
        mock_umount.return_value = True
        # setup snapshot class
        apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(self.testdir, "data", "fstab"))
        # hack to replace low level snapshot command with a working copy func
        # that reports back on its working
        self.new_parent = None
        self.args = []
        def mock_snapshot(source, dest):
            shutil.copytree(source, dest, symlinks=True)
            self.new_parent = os.path.split(dest)
            self.args = source, dest
            return True
        apt_btrfs.commands.btrfs_subvolume_snapshot = mock_snapshot
        # use it
        res = apt_btrfs.create_btrfs_root_snapshot()
        # check results
        self.assertTrue(res)
        self.assertTrue(os.path.exists(os.path.join(*self.new_parent)))
        parent_file = os.path.join(copy_of_model_root, "@", "etc", 
            "apt-btrfs-parent")
        self.assertEqual(os.readlink(parent_file), 
            "../../%s" % self.new_parent[1])
        self.assertTrue(len(self.args), 2)
        self.assertTrue(self.args[0].endswith("@"))
        self.assertTrue("@apt-snapshot-" in self.args[1])
        #shutil.rmtree(copy_of_model_root)

    @mock.patch('apt_btrfs_snapshot.LowLevelCommands')
    @mock.patch('apt_btrfs_snapshot.AptBtrfsSnapshot.mount_btrfs_root_volume')
    @mock.patch('apt_btrfs_snapshot.AptBtrfsSnapshot.umount_btrfs_root_volume')
    def test_btrfs_set_default(self, mock_umount, mock_mount, 
            mock_commands):
        # make a copy of a model btrfs subvol tree
        model_root = os.path.join(self.testdir, "data", "model_root")
        copy_of_model_root = os.path.join(self.testdir, "data", "root3")
        if os.path.exists(copy_of_model_root):
            shutil.rmtree(copy_of_model_root)
        shutil.copytree(model_root, copy_of_model_root, symlinks=True)
        # setup mock
        mock_mount.return_value = copy_of_model_root
        mock_umount.return_value = True
        # setup snapshot class
        apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(self.testdir, "data", "fstab"))
        # hack to replace low level snapshot command with a working copy func
        # that reports back on its working
        old_listdir = os.listdir(copy_of_model_root)
        self.new_parent = None
        self.args = []
        def mock_snapshot(source, dest):
            shutil.copytree(source, dest, symlinks=True)
            if source == "@":
                self.backup = os.path.split(dest)
            else:
                self.new_parent = os.path.split(source)
            self.args = source, dest
            return True
        apt_btrfs.commands.btrfs_subvolume_snapshot = mock_snapshot
        # use it
        res = apt_btrfs.set_default("@apt-snapshot-2013-08-01_19:53:16")
        # check results
        self.assertTrue(res)
        # check for backup existance (hard) and its parent (easy)
        new_listdir = os.listdir(copy_of_model_root)
        for i in new_listdir:
            if not i in old_listdir:
                parent_file = os.path.join(copy_of_model_root, i, "etc", 
                    "apt-btrfs-parent")
                self.assertEqual(os.readlink(parent_file), 
                    "../../@apt-snapshot-2013-08-06_13:26:30")
        self.assertTrue(os.path.exists(os.path.join(copy_of_model_root, 
            "@apt-snapshot-2013-08-01_19:53:16")))
        parent_file = os.path.join(copy_of_model_root, "@", "etc", 
            "apt-btrfs-parent")
        self.assertEqual(os.readlink(parent_file), 
            "../../@apt-snapshot-2013-08-01_19:53:16")
        self.assertTrue(len(self.args), 2)
        self.assertTrue(self.args[1].endswith("@"))
        self.assertTrue("@apt-snapshot-" in self.args[0])
        #shutil.rmtree(copy_of_model_root)

    @mock.patch('apt_btrfs_snapshot.LowLevelCommands')
    @mock.patch('apt_btrfs_snapshot.AptBtrfsSnapshot.mount_btrfs_root_volume')
    @mock.patch('apt_btrfs_snapshot.AptBtrfsSnapshot.umount_btrfs_root_volume')
    def test_btrfs_delete_snapshot(self, mock_umount, mock_mount, 
            mock_commands):
        # setup mock
        mock_mount.return_value = os.path.join(self.testdir, "data", "root")
        mock_umount.return_value = True
        mock_commands.btrfs_delete_snapshot.return_value = True
        # do it
        apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(self.testdir, "data", "fstab"))
        res = apt_btrfs.delete_snapshot("@apt-snapshot-2013-08-01_20:42:40")
        self.assertTrue(res)
        self.assertTrue(apt_btrfs.commands.btrfs_delete_snapshot.called)
        (args, kwargs) = apt_btrfs.commands.btrfs_delete_snapshot.call_args
        self.assertTrue(args[0].endswith("/@apt-snapshot-2013-08-01_20:42:40"))

    def test_parser_older_than_to_datetime(self):
        apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(self.testdir, "data", "fstab"))
        t = apt_btrfs._parse_older_than_to_datetime("5d")
        e = datetime.datetime.now() - datetime.timedelta(5)
        # Check that t is within a second of e
        self.assertTrue(e - t < datetime.timedelta(0, 1))
    
    @mock.patch('apt_btrfs_snapshot.AptBtrfsSnapshot.mount_btrfs_root_volume')
    @mock.patch('apt_btrfs_snapshot.AptBtrfsSnapshot.umount_btrfs_root_volume')
    def test_list_snapshots(self, mock_umount, mock_mount):
        # setup mock
        mock_mount.return_value = os.path.join(self.testdir, "data", "root")
        mock_umount.return_value = True
        # do it
        apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(self.testdir, "data", "fstab"))
        self._btrfs_root_mountpoint = os.path.join(
                               self.testdir, "data", "root")
        res = apt_btrfs.get_btrfs_root_snapshots_list()
        dirlist = os.listdir(os.path.join(self.testdir, "data", "root"))
        dirlist = [i for i in dirlist if i.startswith("@apt-snapshot")]
        self.assertEqual(len(res), len(dirlist))
        for i in dirlist:
            self.assertIn(i, res)

    @mock.patch('apt_btrfs_snapshot.AptBtrfsSnapshot.mount_btrfs_root_volume')
    @mock.patch('apt_btrfs_snapshot.AptBtrfsSnapshot.umount_btrfs_root_volume')
    def test_list_snapshots(self, mock_umount, mock_mount):
        # setup mock
        mock_mount.return_value = os.path.join(self.testdir, "data", "root")
        mock_umount.return_value = True
        # do it
        apt_btrfs = AptBtrfsSnapshot(
            fstab=os.path.join(self.testdir, "data", "fstab"))
        self._btrfs_root_mountpoint = os.path.join(
                               self.testdir, "data", "root")
        older_than = datetime.datetime(2013, 8, 3)
        res = apt_btrfs.get_btrfs_root_snapshots_list(older_than=older_than)
        self.assertEqual(len(res), 10)
        
        older_than = datetime.datetime(2013, 7, 27)
        res = apt_btrfs.get_btrfs_root_snapshots_list(older_than=older_than)
        self.assertEqual(len(res), 4)

    
        

if __name__ == "__main__":
    unittest.main()
