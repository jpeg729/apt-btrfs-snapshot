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
import cPickle as pickle
import types
import random

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


class TestSnapshot(unittest.TestCase):

    def setUp(self):
        self.testdir = os.path.dirname(os.path.abspath(__file__))
        # make a copy of a model btrfs subvol tree
        model_root = os.path.join(self.testdir, "data", "model_root")
        self.sandbox_root = os.path.join(self.testdir, "data", "root3")
        if os.path.exists(self.sandbox_root):
            shutil.rmtree(self.sandbox_root)
        shutil.copytree(model_root, self.sandbox_root, symlinks=True)
        snapshots.setup(self.sandbox_root)

    def tearDown(self):
        shutil.rmtree(self.sandbox_root)

    def test_get_children(self):
        res = Snapshot(SNAP_PREFIX + "2013-07-31_00:00:04").children
        self.assertEqual(len(res), 2)
        expected = [SNAP_PREFIX + "2013-08-01_19:53:16",
            SNAP_PREFIX + "2013-07-31_12:53:16-raring-to-go"]
        for i in res:
            self.assertIn(i.name, expected)
        self.assertEqual(res, 
            snapshots.children[SNAP_PREFIX + "2013-07-31_00:00:04"])

    def test_get_parent(self):
        res = Snapshot(SNAP_PREFIX + "2013-07-31_00:00:04").parent
        self.assertEqual(res.name, SNAP_PREFIX + "2013-07-26_14:50:53", 
            snapshots.parents[SNAP_PREFIX + "2013-07-31_00:00:04"].name)
        self.assertIn("@", snapshots.parents.keys())
        
    def test_parse_orphans(self):
        snapshots._parse_tree()
        self.assertEqual(len(snapshots.orphans), 3)

    def test_set_parent(self):
        child = SNAP_PREFIX + "2013-07-31_12:53:16-raring-to-go"
        Snapshot(child).parent = None
        parent_file = os.path.join(self.sandbox_root, 
            SNAP_PREFIX + "2013-07-31_12:53:16-raring-to-go", PARENT_LINK)
        self.assertFalse(os.path.exists(parent_file))
        Snapshot(child).parent = SNAP_PREFIX + "2013-07-26_14:50:53"
        self.assertEqual(os.readlink(parent_file), 
            os.path.join(PARENT_DOTS, SNAP_PREFIX + "2013-07-26_14:50:53"))

    def test_list_snapshots(self):
        res = [s.name for s in snapshots.get_list()]
        dirlist = os.listdir(snapshots.mp)
        expected = [i for i in dirlist if i.startswith(SNAP_PREFIX)]
        expected.remove(u'@apt-snapshot-xxxx-xx-xx_xx:xx:xx-bad-date')
        expected.remove(u'@apt-snapshot-bad-date')
        self.assertItemsEqual(expected, res)
        
    def test_list_snapshots_older_than(self):
        older_than = datetime.datetime(2013, 8, 3)
        res = snapshots.get_list(older_than=older_than)
        self.assertEqual(len(res), 5)
        for i in res:
            self.assertTrue(i.date < older_than)
        
        older_than = datetime.datetime(2013, 7, 27)
        res = snapshots.get_list(older_than=older_than)
        for i in res:
            self.assertTrue(i.date < older_than)
        self.assertEqual(len(res), 1)
        
        res = snapshots.get_list()
        self.assertEqual(len(res), 16)
        
        older_than = "2013-08-07_18:00:42"
        res = snapshots.get_list(older_than=older_than)
        older_than = datetime.datetime(2013, 8, 7, 18, 0, 42)
        self.assertEqual(len(res), 8)
        for i in res:
            self.assertTrue(i.date < older_than)
    
    def test_hash_eq_and_dictionary_keys(self):
        snapname = SNAP_PREFIX + "2013-07-26_14:50:53"
        snapshot = Snapshot(snapname)
        self.assertEqual(hash(snapshot), 
            hash(datetime.datetime(2013, 7, 26, 14, 50, 53)))
        self.assertEqual(snapshot, Snapshot(snapname))
        self.assertNotEqual(snapshot, Snapshot(snapname + "tag"))
        d = {}
        d[snapshot] = 3
        self.assertIn(Snapshot(snapname), d)
        self.assertEqual(d[Snapshot(snapname)], d[snapshot], 3)
    
    def test_tag(self):
        tagged = Snapshot(SNAP_PREFIX + "2013-07-31_12:53:16-raring-to-go")
        not_tagged = Snapshot(SNAP_PREFIX + "2013-07-26_14:50:53")
        self.assertEqual(tagged.tag, "raring-to-go")
        self.assertEqual(not_tagged.tag, "")

    def test_will_delete(self):
        list_of = snapshots.list_of
        random.shuffle(list_of)
        for snap in list_of:
            parent = snap.parent
            children = snap.children
            snap.will_delete()
            self.assertNotIn(snap, snapshots.list_of)
            self.assertNotIn(snap.name, snapshots.parents)
            self.assertNotIn(snap.name, snapshots.children)
            for child in children:
                self.assertEqual(child.parent, parent)
                if parent != None:
                    self.assertIn(child, parent.children)
            snapshots.setup(self.sandbox_root)


if __name__ == "__main__":
    unittest.main()
