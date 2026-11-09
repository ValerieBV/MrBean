from django.core.files.base import ContentFile
from django.test import RequestFactory, SimpleTestCase
from .media import private_media_response


class PrivateRangeTests(SimpleTestCase):
    data = b'0123456789abcdef'

    def response(self, value=None):
        request = RequestFactory().get('/', **({'HTTP_RANGE':value} if value is not None else {}))
        return private_media_response(ContentFile(self.data, name='recording.mp3'), request)

    def test_full_response_advertises_seeking_and_keeps_private_headers(self):
        response = self.response()
        self.assertEqual(response.status_code,200)
        self.assertEqual(response['Accept-Ranges'],'bytes')
        self.assertEqual(response['Cache-Control'],'private, no-store')
        self.assertEqual(b''.join(response.streaming_content),self.data)
        response.close()

    def test_prefix_middle_suffix_and_open_ended_ranges(self):
        for header, expected, content_range in [('bytes=0-3',b'0123','bytes 0-3/16'),
                ('bytes=7-11',b'789ab','bytes 7-11/16'), ('bytes=-4',b'cdef','bytes 12-15/16'),
                ('bytes=12-',b'cdef','bytes 12-15/16'), ('bytes=14-100',b'ef','bytes 14-15/16')]:
            with self.subTest(header=header):
                response=self.response(header)
                self.assertEqual(response.status_code,206)
                self.assertEqual(response['Content-Range'],content_range)
                self.assertEqual(int(response['Content-Length']),len(expected))
                self.assertEqual(b''.join(response.streaming_content),expected)
                response.close()

    def test_invalid_or_unsatisfiable_ranges_are_bounded(self):
        for header in ['bytes=30-','bytes=8-3','bytes=-0','bytes=0-1,4-5','bytes=-','invalid','bytes='+'9'*200+'-']:
            response=self.response(header)
            self.assertEqual(response.status_code,416)
            self.assertEqual(response['Content-Range'],'bytes */16')
