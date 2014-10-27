#!/usr/bin/python
# Copyright 2014 - Brian J. Donohoe
#
# This file is part of bang.
#
# bang is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# bang is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with bang.  If not, see <http://www.gnu.org/licenses/>.


import unittest
from boto.sqs.message import Message
# from yaml import ParserError
from bang.sqslistener.request_message import RequestMessage
from bang.sqslistener.request_message import RequestMessageException
from bang.sqslistener.request_message import MissingDataRequestMessageException
from bang.sqslistener.request_message import EmptyBodyRequestMessageException
from bang.sqslistener.request_message import NoneMessageRequestMessageException
from bang.sqslistener.request_message import MissingJobNameRequestMessageException


class TestRequestMessage(unittest.TestCase):

    def test_parse_yaml(self):

        message_body=("---\n"
                      "test_job_1:\n"
                      "  request_id: asdfjkl;test\n"
                      "  parameters:\n"
                      "    - one\n"
                      "    - two\n"
                      "    - three\n")

        message = Message(body=message_body)

        request_message = RequestMessage(message)

        assert request_message.job_name == 'test_job_1'
        assert request_message.request_id == 'asdfjkl;test'
        assert request_message.job_parameters[0] == 'one'
        assert request_message.job_parameters[1] == 'two'
        assert request_message.job_parameters[2] == 'three'


    def test_parse_yaml_missing_request_id(self):

        # Every request message needs to have a request_id
        message_body_bad = ("---\n"
                            "test_job_1:\n"
                            "\n")

        bad_message = Message(body=message_body_bad)  # Bad message to test exception throwing with

        with self.assertRaises(RequestMessageException):
            request_message = RequestMessage(Message(body=message_body_bad))

    def test_parse_yaml_with_params_missing_request_id(self):

        # Every request message needs to have a request_id
        message_body_bad = ("---\n"
                            "test_job_1:\n"
                            "  parameters:\n"
                            "    - one\n"
                            "    - two\n"
                            "    - three\n")

        bad_message = Message(body=message_body_bad)  # Bad message to test exception throwing with

        with self.assertRaises(RequestMessageException):
            request_message = RequestMessage(Message(body=message_body_bad))

    def test_empty_message_body(self):
        message_body_empty = ""
        empty_message = Message(body=message_body_empty)

        with self.assertRaises(RequestMessageException):
            request_message = RequestMessage(empty_message)

    def test_no_key_message_body(self):
        message_body_no_key = "  one"
        message_no_key = Message(body=message_body_no_key)

        with self.assertRaises(MissingJobNameRequestMessageException):
            request_message = RequestMessage(message_no_key)

    def test_none_message_body(self):
        message_body_none = None
        none_body_message = Message(body=message_body_none)

        with self.assertRaises(EmptyBodyRequestMessageException):
            request_message = RequestMessage(none_body_message)

    def test_none_message(self):
        none_body_message = None
        with self.assertRaises(NoneMessageRequestMessageException):
            request_message = RequestMessage(none_body_message)

    def test_missing_job_name_yaml_key(self):
        job_name_missing_body = ("---\n"
                                 "  request_id: asdfjkl;test\n"
                                 "  parameters:\n"
                                 "    - one\n"
                                 "    - two\n"
                                 "    - three\n")
        job_name_missing_message = Message(body=job_name_missing_body)
        with self.assertRaises(RequestMessageException): # TODO Should be MissingJobNameRequestMessageException
            # TODO: Exception is actually being raised at missing request Id because it thinks parameters is the key name.
            request_message = RequestMessage(job_name_missing_message)


    def test_missing_request_content(self):
        missing_content_body = ("---\n"
                                 "test_job_1:\n")
        missing_content_message = Message(body=missing_content_body)
        with self.assertRaises(MissingDataRequestMessageException):
            request_message = RequestMessage(missing_content_message)

