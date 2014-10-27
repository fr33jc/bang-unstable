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
#

from boto.sqs.message import Message
from non_daemonized_pool import MyPool
from request_message import RequestMessage
from request_message import RequestMessageException
from response_message import ResponseMessage
from sqsjobs import SQSJobError
from sqsjobs import SQSJobs
from sqsmultiprocessutils import start_job_process
import boto.sqs
import logging
import logging.config
import os
import response_states
import sys
import time
import yaml

DEFAULT_POOL_PROCESSES = 5
DEFAULT_CONFIG_LEVEL = logging.INFO
DEFAULT_LOGGING_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'


class SQSListenerException(Exception):
    pass


class MissingQueueException(Exception):
    pass


class SQSListener:
    """The SQS Listener is a tool for polling Amazon's SQS service for bang-stacks to be run."""

    def __init__(self,
                 listener_config_path=os.path.join(os.environ['HOME'], '.sqslistener'),  # eg. /home/user/.sqslistener
                 jobs_config_path='/home/bang-dispatcher/jobs.yml',
                 logging_config_path='/home/bang-dispatcher/logging-config',     # If None, it will log to stderr.
                 aws_region='us-east-1',
                 queue_name='bang-queue',
                 response_queue_name='bang-response',
                 polling_interval=2):  # in seconds

        """SQSListener Constructor
        :param listener_config_path:    The primary config file path for the SQSListener which contains information
                                            about other config files and values.
        :param jobs_config_path:        The config file that defines all the jobs and their corresponding bang-stacks
                                            that can be invoked via request messages.
        :param logging_config_path:     Logging configuration yaml file. Logger name must be SQSListener.
        :param aws_region:              Which AWS region to use.
        :param queue_name:              The name in SQS of the request queue to be polled.
        :param response_queue_name:     The name in SQS where response messages will be sent.
        :param polling_interval:        The time in seconds between each poll of the request queue.

        Precedence order for configuration values (Highest to lowest):
                1. In Config file
                2. Passed in in the constructor
                3. Constructor Default
        """
        # Set initial configs based on arguments
        config = dict()
        config['logging_config_path'] = logging_config_path
        config['jobs_config_path'] = jobs_config_path
        config['aws_region'] = aws_region
        config['job_queue_name'] = queue_name
        config['response_queue_name'] = response_queue_name
        config['polling_interval'] = polling_interval

        ### Load SQSListener Configuration ###
        listener_config_yaml = self.load_sqs_listener_config(listener_config_path)
        for key in listener_config_yaml:
            config[key] = listener_config_yaml.get(key)

        ### Setup Logging
        self.logger = self.setup_logging(config.get('logging_config_path'))
        self.logger.info("Starting up SQS Listener...")

        ### Connect to AWS ###
        self.conn = self.connect_to_sqs(config.get('aws_region'))
        self.logger.info("Connecting to request queue: %s" % config.get('job_queue_name'))
        self.queue = self.conn.get_queue(config.get('job_queue_name'))
        self.logger.info("Connecting to response queue: %s" % config.get('response_queue_name'))
        self.response_queue = self.conn.get_queue(config.get('response_queue_name'))

        if not self.queue:
            error_msg = "Queue %s does not exist." % config.get('job_queue_name')
            self.logger.critical(error_msg)
            raise MissingQueueException(error_msg)
        if not self.response_queue:
            error_msg = "Queue %s does not exist." % config.get('response_queue_name')
            self.logger.critical(error_msg)
            raise MissingQueueException(error_msg)

        ### Import Jobs definition ###
        self.logger.info("Importing jobs definition from: %s ..." % config.get('jobs_config_path'))
        self.job_set = SQSJobs()
        self.job_set.load_jobs_from_file(config.get('jobs_config_path'))

        ### Set up polling ###
        self.logger.info("Setting up polling...")
        self.polling_interval = polling_interval
        self.pool = MyPool(processes=DEFAULT_POOL_PROCESSES)

        self.polling = False  # Polling doesn't start until you tell it to.
        self.logger.info("Set up complete.")

    def load_sqs_listener_config(self, listener_config_path):
        """Loads the primary listener config file.
        :param listener_config_path: The path to the listener config file.
        """
        with open(listener_config_path) as f:
            ret = yaml.safe_load(f)
        return ret

    def setup_logging(self, logging_config_path):
        """Sets up logging for the SQSListener by using the path provided, or upon not being able to find the logging
        config file instead uses a default logged-to-stderr logger.
        :logging_config_path: The path to the logging config file.
        """
        if os.path.exists(logging_config_path):
            with open(logging_config_path, 'rt') as f:
                config = yaml.safe_load(f.read())
            logging.config.dictConfig(config)
        else:
            logging.basicConfig(format=DEFAULT_LOGGING_FORMAT, level=DEFAULT_CONFIG_LEVEL)

        return logging.getLogger("SQSListener")


    def connect_to_sqs(self, aws_region):
        """Connects to the AWS Region with the given name.
        :param aws_region: The name of the AWS region to connect to.
        """
        self.logger.info("Connecting to SQS...")
        self.logger.info("Connecting to Region: %s" % aws_region)
        return boto.sqs.connect_to_region(aws_region)

    def post_response(self, response):
        """
        Used to post a response on the response queue.
        :param response: The yaml body for the response message.

        """
        message = Message()
        message.set_body(response)

        self.logger.info("Posting response:\n%s" % str(response))
        self.response_queue.write(message)

    def poll_queue(self):
        """Poll the request message queue one, grabbing the first job off the top. By default, boto's get_messages only
        gets a single message at a time.
        """
        polling_response = self.queue.get_messages()

        for message in polling_response:
            self.process_message(message)
            self.logger.info("Deleting received message from queue.")
            self.queue.delete_message(message)

    def process_message(self, message):
        """Process_message takes a boto library Message object, processes it appropriately based on the job definitions
        and then returns an appropriate message based on success or failure.
        :param message: The boto Message to process.
        """
        try:
            request_message = RequestMessage(message)
            self.logger.info("Processing message %s for job %s" % (request_message.request_id,
                                                                   request_message.job_name))

            job = self.job_set.generate_job(request_message.job_name, request_message.job_parameters)

            started_response_message = ResponseMessage(job_name=request_message.job_name,
                                                       request_id=request_message.request_id,
                                                       job_state="started",
                                                       additional_message="Request has been received and the job is in progress.")

            started_response_message_body = started_response_message.dump_yaml()
            self.post_response(started_response_message_body)

            completed_message_body = start_job_process(self.pool,
                                                       job,
                                                       request_message.request_id,
                                                       self.response_queue,
                                                       request_message)
            request_id = request_message.request_id
            self.logger.info("Sending message to response queue: %s" % request_id)
            self.post_response(completed_message_body)
        except RequestMessageException, e:
            self.logger.exception(e)
            job_missing_response_message = ResponseMessage(job_name="unknown",
                                                           request_id="unknown",
                                                           job_state=response_states.failure,
                                                           additional_message="Invalid Message: %s" % str(e))
            response_body = job_missing_response_message.dump_yaml()
            self.post_response(response_body)
        except SQSJobError, e:
            self.logger.error("An error occurred with the job: %s", str(e))
            job_missing_response_message = ResponseMessage(job_name=request_message.job_name,
                                                           request_id=request_message.request_id,
                                                           job_state=response_states.failure,
                                                           additional_message="Job definition is missing.")
            response_body = job_missing_response_message.dump_yaml()
            self.post_response(response_body)
        except Exception, e:
            self.logger.error("An error occurred processing a message: %s", str(e))

            if type(message) is boto.sqs.message.Message:
                msg = message.get_body()
            else:
                msg = str(message)

            job_missing_response_message = ResponseMessage(job_name='unknown',
                                                           request_id='unknown',
                                                           job_state=response_states.failure,
                                                           additional_message="There was a problem with your request Message, %s:\n%s"% (str(e), msg))
            response_body = job_missing_response_message.dump_yaml()
            self.post_response(response_body)

    def start_polling(self):
        """Begin the main SQSListener polling loop."""

        self.logger.info("Starting polling...")
        self.polling = True

        while self.polling:
            self.poll_queue()
            time.sleep(self.polling_interval)

        self.logger.info("Polling stopped.")
