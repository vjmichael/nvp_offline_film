"""No recursive pywebview exposure of native index, window or host state."""
import unittest
import inspect
from tools.nvp_desktop_alpha import ReviewedWebViewAPI


class WebViewBridgeFacadeTests(unittest.TestCase):
    def test_only_public_class_methods_are_exported(self):
        class NativeHost:
            def __init__(self):
                self.index = self
                self.window = self
                self.origin = "http://127.0.0.1:1234"
            def camera_render_capabilities(self):
                return {"status": "host-verified"}
            def film02mf_catalog(self, project_id):
                return {"project_id": project_id}
            def _close(self):
                raise AssertionError("Not a browser method")
            @property
            def dangerous_public_property(self):
                raise AssertionError("No property may be traversed")
        host = NativeHost()
        api = ReviewedWebViewAPI(host)
        self.assertEqual(dir(api),
                         ["camera_render_capabilities", "film02mf_catalog"])
        self.assertEqual(api.camera_render_capabilities(),
                         {"status": "host-verified"})
        self.assertEqual(api.film02mf_catalog("original_project"),
                         {"project_id": "original_project"})
        for forbidden in ("index", "window", "origin",
                          "dangerous_public_property", "_close"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, dir(api))
                with self.assertRaises(AttributeError):
                    getattr(api, forbidden)
        self.assertTrue(inspect.ismethod(api.film02mf_catalog))

    def test_real_pywebview_function_walker_never_enters_host_graph(self):
        try:
            from webview.util import get_functions
        except ImportError:
            self.skipTest("pywebview available in native Windows dependency gate")
        class NativeHost:
            def __init__(self):
                self.index = self
                self.window = self
            def film02mf_catalog(self, project_id):
                return {"project_id": project_id}
        exported = get_functions(ReviewedWebViewAPI(NativeHost()))
        self.assertIn("film02mf_catalog", exported)
        self.assertFalse(any("index" in item or "window" in item
                             for item in exported))


if __name__ == "__main__":
    unittest.main()
