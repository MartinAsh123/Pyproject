"""Offline regression tests; OS providers and all network calls are mocked."""

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import socket
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import urllib.error

import main


class FileTests(unittest.TestCase):
    def test_empty_directory_and_fewer_than_five_entries(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            self.assertEqual(main.largest_items(path, 5), [])
            (path / "small.bin").write_bytes(b"s" * 2)
            (path / "larger.bin").write_bytes(b"l" * 20)
            (path / "nested").mkdir()
            (path / "nested" / "file.bin").write_bytes(b"n" * 10)
            items = main.largest_items(path, 5)
            self.assertEqual([(item.name, item.size) for item in items], [
                ("larger.bin", 20), ("nested", 10), ("small.bin", 2),
            ])
            self.assertEqual(len(main.largest_items(path, 1)), 1)

    def test_symlinks_are_not_counted(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / "file").write_bytes(b"12345")
            try:
                (path / "link").symlink_to(path / "file")
            except (OSError, NotImplementedError):
                self.skipTest("symbolic links unavailable")
            self.assertEqual(main.directory_size(path), (5, False))
            self.assertEqual([item.name for item in main.largest_items(path, 5)], ["file"])

    def test_walk_permission_error_marks_size_partial(self):
        report = Mock()
        def failing_walk(path, **kwargs):
            kwargs["onerror"](PermissionError(13, "denied", "private"))
            return iter(())
        with patch.object(main.os, "walk", side_effect=failing_walk):
            self.assertEqual(main.directory_size("private", report), (0, True))
        report.assert_called_once()

    def test_disappearing_file_marks_size_partial(self):
        report = Mock()
        with patch.object(main.os, "walk", return_value=[("root", [], ["gone"])]), \
                patch.object(Path, "lstat", side_effect=FileNotFoundError(2, "gone", "root/gone")):
            self.assertEqual(main.directory_size("root", report), (0, True))
        report.assert_called_once()

    def test_unreadable_root_does_not_crash(self):
        report = Mock()
        with patch.object(main.os, "scandir", side_effect=PermissionError("denied")):
            self.assertEqual(main.largest_items("private", 5, report), [])
        report.assert_called_once()

    def test_binary_units(self):
        self.assertEqual(main.human_size(1024), "1.00 KiB")
        self.assertEqual(main.human_size(2 ** 30), "1.00 GiB")


class NetworkTests(unittest.TestCase):
    def test_public_ip_is_validated_and_has_timeout(self):
        response = Mock()
        response.read.return_value = b"203.0.113.7\n"
        with patch.object(main.urllib.request, "urlopen") as request:
            request.return_value.__enter__.return_value = response
            self.assertEqual(main.public_ip(2.5), "203.0.113.7")
            self.assertEqual(request.call_args.kwargs["timeout"], 2.5)
            response.read.assert_called_once_with(128)

    def test_public_ip_errors_are_nonfatal(self):
        for error in (TimeoutError("timeout"), urllib.error.URLError("offline")):
            with self.subTest(error=error):
                report = Mock()
                with patch.object(main.urllib.request, "urlopen", side_effect=error):
                    self.assertIsNone(main.public_ip(1, report))
                report.assert_called_once()

    def test_public_ip_rejects_invalid_response(self):
        response = Mock()
        response.read.return_value = b"<html>proxy error</html>"
        report = Mock()
        with patch.object(main.urllib.request, "urlopen") as request:
            request.return_value.__enter__.return_value = response
            self.assertIsNone(main.public_ip(1, report))
        report.assert_called_once()

    def test_linux_ipv4_ipv6_and_multiple_routes(self):
        with patch.object(main, "run_json", side_effect=[
            [{"gateway": "192.0.2.1", "dev": "eth0", "metric": 100},
             {"dev": "tun0", "metric": 200}],
            [{"gateway": "fe80::1", "dev": "eth0", "metric": 100}],
        ]) as run:
            self.assertEqual(main.default_routes("Linux", 3), [
                ("IPv4", "192.0.2.1", "eth0", 100),
                ("IPv4", "on-link", "tun0", 200),
                ("IPv6", "fe80::1", "eth0", 100),
            ])
            self.assertEqual(run.call_args_list[0].args, (["ip", "-j", "-4", "route", "show", "default"], 3))
            self.assertIn("-6", run.call_args_list[1].args[0])

    def test_linux_multipath_route_keeps_each_interface(self):
        with patch.object(main, "run_json", side_effect=[
            [{"metric": 100, "nexthops": [
                {"gateway": "192.0.2.1", "dev": "eth0"},
                {"gateway": "198.51.100.1", "dev": "eth1"},
            ]}], [],
        ]):
            self.assertEqual(main.default_routes("Linux", 1), [
                ("IPv4", "192.0.2.1", "eth0", 100),
                ("IPv4", "198.51.100.1", "eth1", 100),
            ])

    def test_windows_single_json_route_and_localized_alias(self):
        row = {"DestinationPrefix": "0.0.0.0/0", "NextHop": "192.0.2.1",
               "InterfaceAlias": "רשת מקומית", "InterfaceIndex": 3, "RouteMetric": 0}
        with patch.object(main, "run_json", return_value=row) as run:
            self.assertEqual(main.default_routes("Windows", 5), [
                ("IPv4", "192.0.2.1", "רשת מקומית", 0),
            ])
            command = run.call_args.args[0]
            self.assertEqual(command[0], "powershell.exe")
            self.assertIn("Get-NetRoute", command[-1])
            self.assertNotIn("ipconfig", command[-1])

    def test_route_command_failure_is_nonfatal(self):
        report = Mock()
        with patch.object(main, "run_json", side_effect=[
            FileNotFoundError("ip unavailable"),
            subprocess.TimeoutExpired("ip", 1),
        ]):
            self.assertEqual(main.default_routes("Linux", 1, report), [])
        self.assertEqual(report.call_count, 2)

    def test_malformed_route_output_is_nonfatal(self):
        report = Mock()
        with patch.object(main, "run_json", return_value={"NextHop": "bad"}):
            self.assertEqual(main.default_routes("Windows", 1, report), [])
        report.assert_called_once()

    def test_json_subprocess_has_timeout_and_no_shell(self):
        with patch.object(main.subprocess, "run", return_value=SimpleNamespace(stdout='[{"dev":"eth0"}]')) as run:
            self.assertEqual(main.run_json(["ip", "-j"], 4), [{"dev": "eth0"}])
            self.assertEqual(run.call_args.kwargs["timeout"], 4)
            self.assertTrue(run.call_args.kwargs["check"])
            self.assertNotIn("shell", run.call_args.kwargs)

    def test_all_interface_addresses_are_reported(self):
        provider = SimpleNamespace(
            net_if_addrs=Mock(return_value={
                "eth0": [SimpleNamespace(family=socket.AF_INET, address="192.0.2.2"),
                         SimpleNamespace(family=socket.AF_INET6, address="fe80::2%eth0")],
                "vpn": [SimpleNamespace(family=socket.AF_INET, address="198.51.100.2")],
            }),
            net_if_stats=Mock(return_value={"eth0": SimpleNamespace(isup=True), "vpn": SimpleNamespace(isup=False)}),
            Error=RuntimeError,
        )
        with patch.object(main, "psutil", provider):
            self.assertEqual(main.interface_addresses(), [
                ("eth0", "up", "IPv4", "192.0.2.2"),
                ("eth0", "up", "IPv6", "fe80::2%eth0"),
                ("vpn", "down", "IPv4", "198.51.100.2"),
            ])


class CLITests(unittest.TestCase):
    def test_invalid_numeric_options(self):
        for arguments in (["--top", "0"], ["--interval", "0"], ["--interval", "nan"], ["--timeout", "inf"]):
            with self.subTest(arguments=arguments), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    main.parser().parse_args(arguments)
                self.assertEqual(raised.exception.code, 2)

    def test_once_skip_network_and_disk_error(self):
        output, errors = io.StringIO(), io.StringIO()
        provider = SimpleNamespace(cpu_percent=Mock(return_value=12.5), Error=RuntimeError)
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(main, "psutil", provider), \
                patch.object(main, "interface_addresses", return_value=[]), \
                patch.object(main, "default_routes", return_value=[]), \
                patch.object(main, "public_ip") as public, \
                patch.object(main.shutil, "disk_usage", side_effect=PermissionError("denied")), \
                redirect_stdout(output), redirect_stderr(errors):
            self.assertEqual(main.main(["--path", folder, "--once", "--skip-public-ip", "--interval", "0.1"]), 0)
        public.assert_not_called()
        provider.cpu_percent.assert_called_once_with(interval=0.1)
        self.assertIn("Public IP: skipped", output.getvalue())
        self.assertIn("12.5%", output.getvalue())
        self.assertIn("Disk usage unavailable", errors.getvalue())

    def test_public_ip_is_printed(self):
        output = io.StringIO()
        provider = SimpleNamespace(cpu_percent=Mock(return_value=0), Error=RuntimeError)
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(main, "psutil", provider), \
                patch.object(main, "interface_addresses", return_value=[]), \
                patch.object(main, "default_routes", return_value=[]), \
                patch.object(main, "public_ip", return_value="203.0.113.9"), \
                redirect_stdout(output):
            self.assertEqual(main.main(["--path", folder, "--once"]), 0)
        self.assertIn("Public IP: 203.0.113.9", output.getvalue())
        self.assertIn("Total:", output.getvalue())
        self.assertIn("Used:", output.getvalue())
        self.assertIn("Free:", output.getvalue())

    def test_help_works_without_optional_dependency(self):
        with patch.object(main, "psutil", None), redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                main.main(["--help"])
        self.assertEqual(raised.exception.code, 0)

    def test_missing_dependency_reports_install_command(self):
        errors = io.StringIO()
        with patch.object(main, "psutil", None), redirect_stderr(errors):
            with self.assertRaises(SystemExit) as raised:
                main.main(["--once"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("pip install -r requirements.txt", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
