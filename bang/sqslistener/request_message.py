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

import yaml
import logging

logger = logging.getLogger("SQSListener")


class RequestMessageException(Exception):
    pass

class EmptyBodyRequestMessageException(RequestMessageException):
    pass

class MissingJobNameRequestMessageException(RequestMessageException):
    pass


class RequestMessage:
    def __init__(self, message):
        yaml_message_body = message.get_body()
        self.job_name = None
        self.request_id = None
        self.job_parameters = None
        self.parse_yaml(yaml_message_body)

    # Raise helpful error messages to be seen by response-queue consumer/client.
    def parse_yaml(self, message_body):
        if not message_body:
            raise EmptyBodyRequestMessageException("Message must have message body.")

        yaml_message_body = yaml.safe_load(message_body)

        try:
            self.job_name = yaml_message_body.keys()[0]
        except AttributeError, e:
            raise MissingJobNameRequestMessageException("Unable to get job name yaml key from request message: %s" % str(e))

        self.request_id = yaml_message_body[self.job_name]['request_id']

        if 'parameters' in yaml_message_body[self.job_name]:
            self.job_parameters = yaml_message_body[self.job_name]["parameters"]
        else:
            self.job_parameters = None

