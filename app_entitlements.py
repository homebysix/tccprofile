#!/usr/bin/python
"""Uses python's pprint to 'pretty print' the entitlements of an app (if they exist) that has been codesigned."""

from __future__ import absolute_import, print_function

import os
import plistlib
import sys
import subprocess

from pprint import pprint


def entitlements(app_obj):
    """Subprocesses the output of codesign on a macOS system and pretty prints the resulting dictionary."""
    app_obj = os.path.expandvars(os.path.expanduser(app_obj))
    if os.path.exists(app_obj):
        cmd = ['/usr/bin/codesign', '-d', '--entitlements', ':-', app_obj]

        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        result, error = process.communicate()

        if process.returncode is 0:
            result = ''.join(result.splitlines()[1:])
            try:
                result = plistlib.readPlistFromString(result)
                return result
            except Exception:
                return 'No entitlements output found in codesigned app.'


usage = '{} [path to code signed object]'.format(sys.argv[0])
if len(sys.argv) > 1:
    if sys.argv[1]:
        pprint(entitlements(sys.argv[1]))
    else:
        print usage
        sys.exit(1)
else:
    print usage
    sys.exit(1)
