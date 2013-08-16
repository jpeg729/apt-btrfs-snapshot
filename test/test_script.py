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
            "create":                  "Function call: create()",
            "create -t tag":           "Function call: create(-tag)",
            "status":                  "Function call: status()",
            "show @snap":              "Function call: show(@snap)",
            "tag @snap name":          "Function call: tag(@snap, -name)",
            "list":                    "Function call: list()",
            "clean":                   "Function call: clean()",
            "tree":                    "Function call: tree()",
            "list-older-than 30d":     "Function call: list_older_than(30d)",
            "set-default snap":        "Function call: set_default(snap, )",
            "set-default snap -t tag": "Function call: set_default(snap, -tag)",
            "rollback":                "Function call: rollback(1, )",
            "rollback -n 5":           "Function call: rollback(5, )",
            "rollback -t tag":         "Function call: rollback(1, -tag)",
            "rollback -n 5 -t tag":    "Function call: rollback(5, -tag)",
            "delete snap":             "Function call: delete(snap)",
            "delete-older-than 5d":    "Function call: delete_older_than(5d)",
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
