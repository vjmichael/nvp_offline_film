"""INDEX-TIME-09: no original paths and no whole-MP4 JS RAM copy.

Tests the exact same FastAPI 206 route used by NVP's installed WebView2.
A controlled native host fixture models a fully verified unapproved file.
No GitHub service and no live camera originals are involved.
"""
from unittest import TestCase,mock
from fastapi import FastAPI,HTTPException
from starlette.requests import Request
from backend.nvp_api import original_source_proxy_range

TICKET="ticket_"+("x"*48)
PORT=42427

class VerifiedHost:
    def __init__(self):
        self.calls=[]
    def stream_info(self,ticket):
        if ticket!=TICKET:raise PermissionError("no native grant")
        return {"format":"nvp.index_time09.native_av_host.v1",
                "status":"VERIFIED_STREAM","total_size":7*1024*1024,
                "media_sha256":"a"*64}
    def stream_range(self,ticket,start,end):
        self.calls.append((ticket,start,end))
        if end-start+1>1024*1024:
            raise ValueError("unbounded native read")
        return b"z"*(end-start+1)

class Window:
    origin=f"http://127.0.0.1:{PORT}"
    def __init__(self):
        self.host=VerifiedHost()
    def _get_av_host(self):
        return self.host

class NativeHTTPRangeTests(TestCase):
    def setUp(self):
        self.app=FastAPI()
        self.native=Window()
        self.app.state.native_av_window=self.native

    def request(self,*,path=None,headers=(),host="127.0.0.1",port=PORT):
        return Request({
            "type":"http","http_version":"1.1","method":"GET",
            "scheme":"http","path":path or
               "/api/native-av-review/"+TICKET+"/media",
            "server":(host,port),
            "headers":[(k.encode("ascii"),v.encode("ascii"))
                       for k,v in headers],
            "app":self.app,
        })

    def test_range_can_seek_forward_without_loading_entire_movie(self):
        response=original_source_proxy_range(TICKET,self.request(
            headers=(("host",f"127.0.0.1:{PORT}"),
                     ("range","bytes=1048576-99999999"),
                     ("sec-fetch-site","same-origin"))))
        self.assertEqual(response.status_code,206)
        self.assertEqual(response.headers["accept-ranges"],"bytes")
        self.assertEqual(response.headers["content-range"],
                         "bytes 1048576-2097151/7340032")
        self.assertEqual(len(response.body),1024*1024)
        self.assertEqual(self.native.host.calls,[(TICKET,1048576,2097151)])
        self.assertEqual(response.headers["cache-control"],"no-store, private")

    def test_no_range_serves_only_first_mib_not_whole_160mb(self):
        response=original_source_proxy_range(TICKET,self.request(
            headers=(("host",f"127.0.0.1:{PORT}"),)))
        self.assertEqual(response.status_code,206)
        self.assertEqual(len(response.body),1024*1024)

    def test_cross_origin_referer_no_ticket_and_no_owner_rejected(self):
        for headers in (
            (("host",f"127.0.0.1:{PORT}"),
             ("origin","https://foreign.example")),
            (("host",f"127.0.0.1:{PORT}"),
             ("sec-fetch-site","cross-site")),
            (("host",f"127.0.0.1:{PORT}"),
             ("referer","http://other.example/")),
        ):
            with self.subTest(headers=headers):
                with self.assertRaises(HTTPException):
                    original_source_proxy_range(TICKET,self.request(headers=headers))
        with self.assertRaises(HTTPException):
            original_source_proxy_range("guess",self.request(
                headers=(("host",f"127.0.0.1:{PORT}"),)))
        self.app.state.native_av_window=None
        with self.assertRaises(HTTPException):
            original_source_proxy_range(TICKET,self.request(
                headers=(("host",f"127.0.0.1:{PORT}"),)))
        self.assertEqual(self.native.host.calls,[])

    def test_mp4_suffix_seek_returns_only_a_verified_short_range(self):
        result=original_source_proxy_range(TICKET,self.request(
            headers=(("host",f"127.0.0.1:{PORT}"),
                     ("range","bytes=-8192"))))
        self.assertEqual(result.status_code,206)
        self.assertEqual(result.headers["content-range"],
                         "bytes 7331840-7340031/7340032")
        self.assertEqual(len(result.body),8192)

    def test_refuse_malformed_multi_range_and_out_of_bounds(self):
        for bad in ("bytes=-0","bytes=20-19","bytes=7000000-",
                    "bytes=0-10,20-30","files=0-1","bytes=x-1"):
            with self.subTest(bad=bad):
                with self.assertRaises(HTTPException):
                    original_source_proxy_range(TICKET,self.request(
                        headers=(("host",f"127.0.0.1:{PORT}"),
                                 ("range",bad))))
