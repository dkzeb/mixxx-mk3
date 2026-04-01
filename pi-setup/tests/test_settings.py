"""Tests for the Settings widget."""
import os
import unittest
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mk3_overlay.widgets.settings import create_settings_widget


class TestSettingsPages(unittest.TestCase):
    def test_has_three_pages(self):
        w = create_settings_widget()
        self.assertEqual(len(w.pages), 3)

    def test_page_titles(self):
        w = create_settings_widget()
        self.assertEqual(w.pages[0].title, "GENERAL")
        self.assertEqual(w.pages[1].title, "LIBRARY")
        self.assertEqual(w.pages[2].title, "NETWORK")

    def test_general_page_items(self):
        w = create_settings_widget()
        labels = [item.label for item in w.pages[0].items]
        self.assertEqual(labels, [
            "Reboot", "Shutdown", "Check for Updates",
            "Auto-update on boot", "Version",
        ])

    def test_reboot_requires_confirm(self):
        w = create_settings_widget()
        self.assertTrue(w.pages[0].items[0].confirm)

    def test_shutdown_requires_confirm(self):
        w = create_settings_widget()
        self.assertTrue(w.pages[0].items[1].confirm)

    def test_check_updates_no_confirm(self):
        w = create_settings_widget()
        self.assertFalse(w.pages[0].items[2].confirm)


class TestNetworkInfo(unittest.TestCase):
    def test_hostname_info(self):
        w = create_settings_widget()
        hostname_item = w.pages[2].items[1]
        self.assertEqual(hostname_item.label, "Hostname")
        with patch("socket.gethostname", return_value="mk3-pi"):
            self.assertEqual(hostname_item.get_value(), "mk3-pi")

    def test_ip_address_info(self):
        w = create_settings_widget()
        ip_item = w.pages[2].items[0]
        self.assertEqual(ip_item.label, "IP Address")

    def test_wifi_info(self):
        w = create_settings_widget()
        wifi_item = w.pages[2].items[2]
        self.assertEqual(wifi_item.label, "WiFi Network")


class TestAutoupdateToggle(unittest.TestCase):
    @patch("builtins.open", MagicMock())
    def test_toggle_on_writes_config(self):
        w = create_settings_widget()
        toggle = w.pages[0].items[3]
        self.assertFalse(toggle.state)
        w.cursor = 3
        w.execute_item()
        self.assertTrue(toggle.state)

    @patch("os.path.exists", return_value=True)
    @patch("os.remove")
    def test_toggle_off_removes_config(self, mock_rm, mock_exists):
        w = create_settings_widget()
        toggle = w.pages[0].items[3]
        toggle.state = True
        w.cursor = 3
        w.execute_item()
        self.assertFalse(toggle.state)

if __name__ == "__main__":
    unittest.main()
