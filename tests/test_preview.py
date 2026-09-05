"""Physical-device preview behavior, using an isolated fake ADB."""
import http.client
import json
import threading
import unittest
import test_coordination as fixtures
import adb_coord as coord
import adb_preview as preview

class PreviewTests(unittest.TestCase):
    setUp = fixtures.CoordinationTests.setUp
    claim = fixtures.CoordinationTests.claim

    def start_server(self, control=False):
        self.current = self.claim()
        self.server = preview.ThreadingHTTPServer(("127.0.0.1", 0), preview.make_handler(
            self.current["serial"], self.current["token"], "preview-key", control))
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, route, method="GET", body=None, headers=None):
        client = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            client.request(method, route, body, headers or {})
            response = client.getresponse()
            return response.status, response.read()
        finally:
            client.close()

    def test_preview_auth_origin_and_revocation(self):
        self.start_server()
        self.assertEqual(self.request("/")[0], 200)
        self.assertEqual(self.request("/frame")[0], 403)
        headers = {"X-ADB-Preview-Key": "preview-key"}
        code, png = self.request("/frame", headers=headers)
        self.assertEqual(code, 200)
        self.assertTrue(png.startswith(b"\x89PNG"))
        self.assertEqual(self.request("/frame", headers={**headers, "Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.request("/frame", headers={**headers, "Host": "evil.example"})[0], 403)
        self.assertEqual(self.request("/input", "POST", "{}", headers)[0], 403)
        coord.change_claim(self.current["serial"], self.current["token"], "release")
        self.assertEqual(self.request("/frame", headers=headers)[0], 409)

    def test_input_validation_and_claim_checks(self):
        self.start_server(control=True)
        headers = {"X-ADB-Preview-Key": "preview-key", "Content-Type": "application/json"}
        self.assertEqual(self.request("/input", "POST", json.dumps({"kind": "tap", "x": 4, "y": 7}), headers)[0], 200)
        self.assertEqual(json.loads((self.root / "argv").read_text())[-5:], ["shell", "input", "tap", "4", "7"])
        for data in [[], {"kind": []}, {"kind": "key", "key": []}, {"kind": "tap", "x": "1; reboot", "y": 1}, {"kind": "key", "key": "POWER"}]:
            self.assertEqual(self.request("/input", "POST", json.dumps(data), headers)[0], 400)
        coord.change_claim(self.current["serial"], self.current["token"], "handoff", "t3:new")
        self.assertEqual(self.request("/input", "POST", json.dumps({"kind": "key", "key": "HOME"}), headers)[0], 409)
