#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import print_function, unicode_literals


import subprocess
import sys
import unittest

sys.path.insert(0, "..")
sys.path.insert(0, ".")



class TestScript(unittest.TestCase):

    def test_commands_that_work(self):
        commands_that_work = { 
            "create":                  "Calls: create()",
            "create -t tag":           "Calls: create(-tag)",
            "status":                  "Calls: status()",
            "show @snap":              "Calls: show(@snap)",
            "tag @snap name":          "Calls: tag(@snap, -name)",
            "list":                    "Calls: list()",
            "clean":                   "Calls: clean()",
            "tree":                    "Calls: tree()",
            "list-older-than 30d":     "Calls: list_older_than(30d)",
            "set-default snap":        "Calls: set_default(snap, )",
            "set-default snap -t tag": "Calls: set_default(snap, -tag)",
            "rollback":                "Calls: rollback(1, )",
            "rollback -n 5":           "Calls: rollback(5, )",
            "rollback -t tag":         "Calls: rollback(1, -tag)",
            "rollback -n 5 -t tag":    "Calls: rollback(5, -tag)",
            "delete snap":             "Calls: delete(snap)",
            "delete-older-than 5d":    "Calls: delete_older_than(5d)",
            "recent":                  "Calls: recent(5, @)",
            "recent -n 3":             "Calls: recent(3, @)",
            "recent -s 3":             "Calls: recent(5, 3)",
            "recent -n 7 -s s":        "Calls: recent(7, s)",
        }
        for cmd, expected in commands_that_work.items():
            args = ["../apt-btrfs-snapshot", "--test"]
            args.extend(cmd.split(" "))
            out = subprocess.check_output(args).strip()
            self.assertEqual(out, expected)
    
    def test_commands_that_fail(self):
        commands_that_fail = { 
            "create tag":           "error: unrecognized arguments: tag",
            "status something":     "error: unrecognized arguments: something",
            "show":                 "error: too few arguments",
            "show @snap fsdk":      "error: unrecognized arguments: fsdk",
            "tag @snap":            "error: too few arguments",
            "list some":            "error: unrecognized arguments: some",
            "clean some":           "error: unrecognized arguments: some",
            "tree seom":            "error: unrecognized arguments: seom",
            "list-older-than":      "error: too few arguments",
            "set-default":          "error: too few arguments",
            "set-default snap tag": "error: unrecognized arguments: tag",
            "rollback 5":           "error: unrecognized arguments: 5",
            "rollback tag":         "error: unrecognized arguments: tag",
            "rollback 5 tag":       "error: unrecognized arguments: 5 tag",
            "delete":               "error: too few arguments",
            "delete-older-than":    "error: too few arguments",
        }
        for cmd, expected in commands_that_fail.items():
            args = ["../apt-btrfs-snapshot", "--test"]
            args.extend(cmd.split(" "))
            with self.assertRaises(subprocess.CalledProcessError) as ex:
                out = subprocess.check_output(args, 
                    stderr=subprocess.STDOUT).strip()
            self.assertTrue(ex.exception.output.strip().endswith(expected))
        


if __name__ == "__main__":
    unittest.main()
