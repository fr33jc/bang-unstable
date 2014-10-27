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
import yaml
from bang.sqslistener.sqsjobs import SQSJobs
from bang.sqslistener.sqsjobs import SQSJobError
from bang.sqslistener.sqsjobs import SQSJobsError


class TestSQSJobs(unittest.TestCase):
    def test_generate_job(self):
        jobs_yaml = yaml.load(
        ( "---\n"
          "test_job_name:\n"
          "  bang-stacks:\n"
          "  - /path/to/first.yml\n"
          "  - /path/to/second.yml\n"))

        job_set = SQSJobs()
        job_set.load_jobs_from_yaml_object(jobs_yaml)
        new_job = job_set.generate_job("test_job_name", ("param1", "param2"))

        self.assertEquals(new_job.name, "test_job_name")
        self.assertEquals(new_job.bang_stacks[0], "/path/to/first.yml")
        self.assertEquals(new_job.bang_stacks[1], "/path/to/second.yml")
        self.assertEquals(new_job.parameters[0], "param1")
        self.assertEquals(new_job.parameters[1], "param2")

    def test_generate_job_missing(self):
        jobs_yaml = yaml.load(
        ( "---\n"
          "test_job_name:\n"
          "  bang-stacks:\n"
          "  - /path/to/first.yml\n"
          "  - /path/to/second.yml\n"))

        job_set = SQSJobs()
        job_set.load_jobs_from_yaml_object(jobs_yaml)

        with self.assertRaises(SQSJobError):
            job_set.generate_job("test_job_name_missing", ("param1", "param2"))

    def test_load_jobs_from_file_missing_file(self):
        job_set = SQSJobs()

        with self.assertRaises(SQSJobsError):
            job_set.load_jobs_from_file('this/file/is/missing')
