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

# A lot of this borrowed from:
#   http://stackoverflow.com/questions/8640959/how-can-i-control-what-scalar-form-pyyaml-uses-for-my-data

import yaml
from collections import OrderedDict


class multiline_literal(str):
    pass


def literal_presenter(dumper, data):
    return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
yaml.add_representer(multiline_literal, literal_presenter)


def response_message_presenter(dumper, data):
    return dumper.represent_dict(data.items())
yaml.add_representer(OrderedDict, response_message_presenter)


class ResponseMessage:
    def __init__(self,
                 job_name,
                 request_id,
                 job_state,  # see: response_states.py
                 additional_message=""):

        self.name = job_name
        self.job_state = job_state
        self.request_id = request_id
        self.message = additional_message

    def dump_yaml(self):
        d = OrderedDict(name=self.name,
                        request_id=self.request_id,
                        result=self.job_state,
                        message=multiline_literal(self.message))

        return yaml.dump(d, explicit_start=True)
