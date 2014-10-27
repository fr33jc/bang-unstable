# Copyright 2014 - Brian J Donohoe
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
from bang.sqslistener.sqslistener import SQSListener
from bang.sqslistener.sqslistener import SQSListenerException
from bang.sqslistener.sqslistener import MissingQueueException
from bang.sqslistener import response_states
import boto
import boto.sqs.connection
from moto import mock_sqs
from mock import MagicMock
from mock import patch
from boto.sqs.message import Message
import yaml

JOBS_CONFIG_PATH = 'tests/resources/sqslistener/jobs.yml'
LISTENER_CONFIG_PATH = 'tests/resources/sqslistener/.sqslistener'

mocked_success_response_body = ("---\n"
                                "job_name: test_job_1\n"
                                "request_id: qwertyasdfjkl;\n"
                                "result: success\n"
                                "message: |-\n"
                                "  Job was mocked!\n")

mocked_failure_response_body = ("---\n"
                                "job_name: test_job_not_there\n"
                                "request_id: qwertyasdfjkl;\n"
                                "result: failure\n"
                                "message: |-\n"
                                "  Job was mocked!\n")

class TestSQSListener(unittest.TestCase):

    def setUp(self):
        self.boto_sqs_patcher = mock_sqs()
        self.MockClass = self.boto_sqs_patcher.start()

        mock_connection = boto.connect_sqs()
        mock_connection.create_queue('bang-queue')
        mock_connection.create_queue('bang-response')

        boto.sqs.connect_to_region = MagicMock(name="mock_connect_to_sqs", return_value=mock_connection)

        self.sqslistener = SQSListener(listener_config_path=LISTENER_CONFIG_PATH)

    def tearDown(self):
        self.boto_sqs_patcher.stop()

    def post_response_test(self):
        test_message_body = "Message Body Test"
        self.sqslistener._post_response(test_message_body)

        try:
            response_message = self.sqslistener.response_queue.get_messages()[0]
        except IndexError:
            raise AssertionError("Response message did not make it onto the queue.")

        assert response_message.get_body() == test_message_body

    @patch('boto.sqs.queue.Queue.get_messages')
    def poll_queue_test(self, mock_get_messages):
        self.sqslistener._poll_queue()
        assert mock_get_messages.called

    def load_sqs_listener_config_test(self):
        test_yaml = self.sqslistener._load_sqs_listener_config('tests/resources/sqslistener/.sqslistener')

        assert test_yaml['aws_region'] == 'us-east-1'
        assert test_yaml['job_queue_name'] == 'bang-queue'
        assert test_yaml['jobs_config_path'] == 'tests/resources/sqslistener/jobs.yml'
        assert test_yaml['logging_config_path'] == 'tests/resources/sqslistener/logging-conf.yml'
        assert test_yaml['polling_interval'] == 2
        assert test_yaml['response_queue_name'] == 'bang-response'

    @patch('bang.sqslistener.sqslistener.start_job_process', return_value=mocked_success_response_body)
    @patch('boto.sqs.queue.Queue.delete_message')
    def process_message_test(self, mock_delete_message, mock_start_job_process):
        message = Message(body=("test_job_1:\n"
                                "  request_id: qwertyasdfjkl;"))

        self.sqslistener._process_message(message)

        assert mock_start_job_process.called
        assert mock_delete_message.called

    @patch('bang.sqslistener.sqslistener.start_job_process', return_value=mocked_failure_response_body)
    @patch('boto.sqs.queue.Queue.delete_message')
    def process_message_test_job_missing(self, mock_delete_message, mock_start_job_process):
        message = Message(body=("test_job_not_there:\n"
                                "  request_id: qwertyasdfjkl;"))

        self.sqslistener._process_message(message)

        # Note: 'A started' message does not get put on the queue if the job is missing.
        for msg in self.sqslistener.response_queue.get_messages():
            msg_yaml = yaml.load(msg.get_body())
            assert msg_yaml['result'] == response_states.failure

    def load_sqs_listener_config_test_none_path(self):
        with patch.dict('os.environ', {'HOME': 'tests/resources/sqslistener/fake-home'}):
            test_yaml = self.sqslistener._load_sqs_listener_config(listener_config_path=None)
            assert test_yaml['aws_region'] == 'us-east-1-fake-home'
            assert test_yaml['job_queue_name'] == 'bang-queue-fake-home'
            assert test_yaml['jobs_config_path'] == 'tests/resources/sqslistener/jobs-fake-home.yml'
            assert test_yaml['logging_config_path'] == 'tests/resources/sqslistener/logging-conf-fake-home.yml'
            assert test_yaml['polling_interval'] == 4
            assert test_yaml['response_queue_name'] == 'bang-response-fake-home'

    def load_sqs_listener_config_test_missing_file(self):
        with self.assertRaises(SQSListenerException):
            self.sqslistener._load_sqs_listener_config(listener_config_path='this/path/doesnt/exist')

    def setup_logging_test(self):
        logger = self.sqslistener._setup_logging('tests/resources/sqslistener/logging-conf.yml')
        # TODO finish

    def setup_logging_missing_test(self):
        logger = self.sqslistener._setup_logging('this/file/does/not/exist/logging-conf.yml')
        # TODO finish

    @patch('bang.sqslistener.sqslistener.SQSListener.process_message')
    def poll_queue_test(self, mock_process_message):
        example_message_body = "---\ntest_job_name:\n  request_id: testrequestid\n"
        message = Message()
        message.set_body(example_message_body)
        self.sqslistener.queue.write(message)
        self.sqslistener.poll_queue()
        assert mock_process_message.called


class TestSQSListenerNoSetup(unittest.TestCase):

    def test_missing_request_queue(self):
        boto_sqs_patcher = mock_sqs()
        mockClass = boto_sqs_patcher.start()

        mock_connection = boto.connect_sqs()
        mock_connection.create_queue('bang-queue')

        boto.sqs.connect_to_region = MagicMock(name="mock_connect_to_sqs", return_value=mock_connection)

        with self.assertRaises(MissingQueueException):
            self.sqslistener = SQSListener(listener_config_path=LISTENER_CONFIG_PATH)

        boto_sqs_patcher.stop()

    def test_missing_response_queue(self):
        boto_sqs_patcher = mock_sqs()
        mockClass = boto_sqs_patcher.start()

        mock_connection = boto.connect_sqs()
        mock_connection.create_queue('response-queue')

        boto.sqs.connect_to_region = MagicMock(name="mock_connect_to_sqs", return_value=mock_connection)

        with self.assertRaises(MissingQueueException):
            self.sqslistener = SQSListener(listener_config_path=LISTENER_CONFIG_PATH)

        boto_sqs_patcher.stop()
