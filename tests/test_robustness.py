import socket
import subprocess
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from llm_wiki import net, verify  # noqa: E402


class RetryTest(unittest.TestCase):
    def test_retries_dns_failure_then_succeeds(self):
        dns = urllib.error.URLError(socket.gaierror(11001, "getaddrinfo failed"))
        with mock.patch.object(net.urllib.request, "urlopen", side_effect=[dns, "OK"]) as opened, \
                mock.patch.object(net.time, "sleep"):
            self.assertEqual(net.urlopen("https://x", timeout=1), "OK")
        self.assertEqual(opened.call_count, 2)

    def test_gives_up_after_limit(self):
        dns = urllib.error.URLError(socket.gaierror(11001, "getaddrinfo failed"))
        with mock.patch.object(net.urllib.request, "urlopen", side_effect=dns) as opened, \
                mock.patch.object(net.time, "sleep"), self.assertRaises(urllib.error.URLError):
            net.urlopen("https://x", timeout=1)
        self.assertEqual(opened.call_count, net.ATTEMPTS)

    def test_http_errors_are_not_retried(self):
        error = urllib.error.HTTPError("https://x", 404, "Not Found", {}, None)
        with mock.patch.object(net.urllib.request, "urlopen", side_effect=error) as opened, \
                mock.patch.object(net.time, "sleep"), self.assertRaises(urllib.error.HTTPError):
            net.urlopen("https://x", timeout=1)
        self.assertEqual(opened.call_count, 1)


class ReadPagesTest(unittest.TestCase):
    def test_form_feeds_inside_a_page_do_not_split_it(self):
        # A real 13-page PDF produced 49 pieces when its output was split on form feeds.
        outputs = [
            subprocess.CompletedProcess([], 0, stdout=("a" * 80 + "\f" + "a" * 80 + "\f").encode()),
            subprocess.CompletedProcess([], 0, stdout=("b" * 80 + "\f").encode()),
        ]
        reader = mock.Mock(pages=[mock.Mock(), mock.Mock()])
        with mock.patch.object(verify.shutil, "which", return_value="pdftotext"), \
                mock.patch("pypdf.PdfReader", return_value=reader), \
                mock.patch.object(verify.subprocess, "run", side_effect=outputs) as run:
            pages = verify.read_pages("x.pdf")
        self.assertEqual(pages, ["a" * 80 + "\n" + "a" * 80, "b" * 80])
        self.assertEqual(run.call_args_list[1].args[0][:7], ["pdftotext", "-enc", "UTF-8", "-f", "2", "-l", "2"])

    def test_one_bad_page_does_not_void_pypdf_result(self):
        good, bad = mock.Mock(), mock.Mock()
        good.extract_text.return_value = "text " * 40
        bad.extract_text.side_effect = RuntimeError("Reached maximum number of tokens per stream.")
        reader = mock.Mock(pages=[good, bad, good])
        with mock.patch.object(verify.shutil, "which", return_value=None), \
                mock.patch("pypdf.PdfReader", return_value=reader):
            self.assertEqual(verify.read_pages("x.pdf"), ["text " * 40, "", "text " * 40])


if __name__ == "__main__":
    unittest.main()
