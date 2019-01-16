#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
test_ember_csi
----------------------------------

Tests for `ember_csi` module.
"""


import unittest

from ember_csi import ember_csi


class TestEmber_csi(unittest.TestCase):

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_fails_no_config(self):
        with self.assertRaises(SystemExit) as asserted:
            ember_csi.main()
        exc = asserted.exception
        self.assertEqual(3, exc.code)
