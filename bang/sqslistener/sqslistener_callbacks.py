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


# Grabbed directly out of ansible's callbacks.py and modified.

from ansible.callbacks import DefaultRunnerCallbacks, PlaybookCallbacks, PlaybookRunnerCallbacks
from ansible import utils
# from ansible.callbacks import #call_callback_module
from ansible.callbacks import banner
import logging
from response_message import ResponseMessage
from boto.sqs.message import Message
import response_states

logger = logging.getLogger("SQSListener")

def display(msg, response_queue, request_message):
    logger.info(msg)

    if response_queue is not None:
        progress_message = ResponseMessage(job_name=request_message.job_name,
                                           request_id=request_message.request_id,
                                           job_state=response_states.working,
                                           additional_message=msg)

        yaml_body = progress_message.dump_yaml()
        message = Message(body=yaml_body)
        response_queue.write(message)

class SQSListenerPlaybookRunnerCallbacks(PlaybookRunnerCallbacks):
    def __init__(self, stats, verbose=None, sqs_response_queue=None, request_message=None):

        if verbose is None:
            verbose = utils.VERBOSITY

        self.verbose = verbose
        self.stats = stats
        self._async_notified = {}

        self.sqs_response_queue = sqs_response_queue
        self.sqs_request_message = request_message

    def on_unreachable(self, host, results):
        delegate_to = self.runner.module_vars.get('delegate_to')
        if delegate_to:
            host = '%s -> %s' % (host, delegate_to)

        item = None
        if type(results) == dict:
            item = results.get('item', None)
        if item:
            msg = "fatal: [%s] => (item=%s) => %s" % (host, item, results)
        else:
            msg = "fatal: [%s] => %s" % (host, results)
        display(msg, self.sqs_response_queue, self.sqs_request_message)
        super(PlaybookRunnerCallbacks, self).on_unreachable(host, results)

    def on_failed(self, host, results, ignore_errors=False):
        delegate_to = self.runner.module_vars.get('delegate_to')
        if delegate_to:
            host = '%s -> %s' % (host, delegate_to)

        results2 = results.copy()
        results2.pop('invocation', None)

        item = results2.get('item', None)
        parsed = results2.get('parsed', True)
        module_msg = ''
        if not parsed:
            module_msg  = results2.pop('msg', None)
        stderr = results2.pop('stderr', None)
        stdout = results2.pop('stdout', None)
        returned_msg = results2.pop('msg', None)

        if item:
            msg = "failed: [%s] => (item=%s) => %s" % (host, item, utils.jsonify(results2))
        else:
            msg = "failed: [%s] => %s" % (host, utils.jsonify(results2))
        display(msg, self.sqs_response_queue, self.sqs_request_message)

        if stderr:
            display("stderr: %s" % stderr, self.sqs_response_queue, self.sqs_request_message)
        if stdout:
            display("stdout: %s" % stdout, self.sqs_response_queue, self.sqs_request_message)
        if returned_msg:
            display("msg: %s" % returned_msg, self.sqs_response_queue, self.sqs_request_message)
        if not parsed and module_msg:
            display("invalid output was: %s" % module_msg, self.sqs_response_queue, self.sqs_request_message)
        if ignore_errors:
            display("...ignoring", self.sqs_response_queue, self.sqs_request_message)
        super(PlaybookRunnerCallbacks, self).on_failed(host, results, ignore_errors=ignore_errors)

    def on_ok(self, host, host_result):
        delegate_to = self.runner.module_vars.get('delegate_to')
        if delegate_to:
            host = '%s -> %s' % (host, delegate_to)

        item = host_result.get('item', None)

        host_result2 = host_result.copy()
        host_result2.pop('invocation', None)
        verbose_always = host_result2.pop('verbose_always', False)
        changed = host_result.get('changed', False)
        ok_or_changed = 'ok'
        if changed:
            ok_or_changed = 'changed'

        # show verbose output for non-setup module results if --verbose is used
        msg = ''
        if (not self.verbose or host_result2.get("verbose_override",None) is not
                None) and not verbose_always:
            if item:
                msg = "%s: [%s] => (item=%s)" % (ok_or_changed, host, item)
            else:
                if 'ansible_job_id' not in host_result or 'finished' in host_result:
                    msg = "%s: [%s]" % (ok_or_changed, host)
        else:
            # verbose ...
            if item:
                msg = "%s: [%s] => (item=%s) => %s" % (ok_or_changed, host, item, utils.jsonify(host_result2, format=verbose_always))
            else:
                if 'ansible_job_id' not in host_result or 'finished' in host_result2:
                    msg = "%s: [%s] => %s" % (ok_or_changed, host, utils.jsonify(host_result2, format=verbose_always))

        if msg != '':
            if not changed:
                display(msg, self.sqs_response_queue, self.sqs_request_message)
            else:
                display(msg, self.sqs_response_queue, self.sqs_request_message)
        super(PlaybookRunnerCallbacks, self).on_ok(host, host_result)

    def on_skipped(self, host, item=None):
        delegate_to = self.runner.module_vars.get('delegate_to')
        if delegate_to:
            host = '%s -> %s' % (host, delegate_to)

        if constants.display_SKIPPED_HOSTS:
            msg = ''
            if item:
                msg = "skipping: [%s] => (item=%s)" % (host, item)
            else:
                msg = "skipping: [%s]" % host
            display(msg, self.sqs_response_queue, self.sqs_request_message)
            super(PlaybookRunnerCallbacks, self).on_skipped(host, item)

    def on_no_hosts(self):
        display("FATAL: no hosts matched or all hosts have already failed -- aborting\n", self.sqs_response_queue, self.sqs_request_message)
        super(PlaybookRunnerCallbacks, self).on_no_hosts()

    def on_async_poll(self, host, res, jid, clock):
        if jid not in self._async_notified:
            self._async_notified[jid] = clock + 1
        if self._async_notified[jid] > clock:
            self._async_notified[jid] = clock
            msg = "<job %s> polling, %ss remaining"%(jid, clock)
            display(msg, self.sqs_response_queue, self.sqs_request_message)
        super(PlaybookRunnerCallbacks, self).on_async_poll(host,res,jid,clock)

    def on_async_ok(self, host, res, jid):
        msg = "<job %s> finished on %s"%(jid, host)
        display(msg, self.sqs_response_queue, self.sqs_request_message)
        super(PlaybookRunnerCallbacks, self).on_async_ok(host, res, jid)

    def on_async_failed(self, host, res, jid):
        msg = "<job %s> FAILED on %s" % (jid, host)
        display(msg, self.sqs_response_queue, self.sqs_request_message)
        super(PlaybookRunnerCallbacks, self).on_async_failed(host,res,jid)

    def on_file_diff(self, host, diff):
        display(utils.get_diff(diff), self.sqs_response_queue, self.sqs_request_message)
        super(PlaybookRunnerCallbacks, self).on_file_diff(host, diff)


class SQSListenerPlaybookCallbacks(PlaybookCallbacks):
    def __init__(self, verbose=False, sqs_response_queue=None, request_message=None):

        if verbose is None:
            verbose = utils.VERBOSITY

        self.verbose = verbose
        self._async_notified = {}

        self.sqs_response_queue = sqs_response_queue
        self.sqs_request_message = request_message

    def on_start(self):
        pass
        #call_callback_module('playbook_on_start')

    def on_notify(self, host, handler):
        pass
        #call_callback_module('playbook_on_notify', host, handler)

    def on_no_hosts_matched(self):
        display("skipping: no hosts matched", self.sqs_response_queue, self.sqs_request_message)
        #call_callback_module('playbook_on_no_hosts_matched')

    def on_no_hosts_remaining(self):
        display("\nFATAL: all hosts have already failed -- aborting", self.sqs_response_queue, self.sqs_request_message)
        #call_callback_module('playbook_on_no_hosts_remaining')

    def on_task_start(self, name, is_conditional):
        msg = "TASK: [%s]" % name
        if is_conditional:
            msg = "NOTIFIED: [%s]" % name

        if hasattr(self, 'start_at'):
            if name == self.start_at or fnmatch.fnmatch(name, self.start_at):
                # we found out match, we can get rid of this now
                del self.start_at
            elif self.task.role_name:
                # handle tasks prefixed with rolenames
                actual_name = name.split('|', 1)[1].lstrip()
                if actual_name == self.start_at or fnmatch.fnmatch(actual_name, self.start_at):
                    del self.start_at

        if hasattr(self, 'start_at'): # we still have start_at so skip the task
            self.skip_task = True
        elif hasattr(self, 'step') and self.step:
            msg = ('Perform task: %s (y/n/c): ' % name).encode(sys.stdout.encoding)
            resp = raw_input(msg)
            if resp.lower() in ['y','yes']:
                self.skip_task = False
                display(banner(msg), self.sqs_response_queue, self.sqs_request_message)
            elif resp.lower() in ['c', 'continue']:
                self.skip_task = False
                self.step = False
                display(banner(msg), self.sqs_response_queue, self.sqs_request_message)
            else:
                self.skip_task = True
        else:
            self.skip_task = False
            display(banner(msg), self.sqs_response_queue, self.sqs_request_message)

        #call_callback_module('playbook_on_task_start', name, is_conditional)

    def on_vars_prompt(self, varname, private=True, prompt=None, encrypt=None, confirm=False, salt_size=None, salt=None, default=None):

        if prompt and default is not None:
            msg = "%s [%s]: " % (prompt, default)
        elif prompt:
            msg = "%s: " % prompt
        else:
            msg = 'input for %s: ' % varname

        def prompt(prompt, private):
            msg = prompt.encode(sys.stdout.encoding)
            if private:
                return getpass.getpass(msg)
            return raw_input(msg)

        if confirm:
            while True:
                result = prompt(msg, private)
                second = prompt("confirm " + msg, private)
                if result == second:
                    break
                display("***** VALUES ENTERED DO NOT MATCH ****", self.sqs_response_queue, self.sqs_request_message)
        else:
            result = prompt(msg, private)

        # if result is false and default is not None
        if not result and default:
            result = default

        if encrypt:
            result = utils.do_encrypt(result, encrypt, salt_size, salt)

        #call_callback_module( 'playbook_on_vars_prompt', varname, private=private, prompt=prompt,
        #                       encrypt=encrypt, confirm=confirm, salt_size=salt_size, salt=None, default=default
        #                    )

        return result

    def on_setup(self):
        display(banner("GATHERING FACTS"), self.sqs_response_queue, self.sqs_request_message)
        #call_callback_module('playbook_on_setup')

    def on_import_for_host(self, host, imported_file):
        msg = "%s: importing %s" % (host, imported_file)
        display(msg, self.sqs_response_queue, self.sqs_request_message)
        #call_callback_module('playbook_on_import_for_host', host, imported_file)

    def on_not_import_for_host(self, host, missing_file):
        msg = "%s: not importing file: %s" % (host, missing_file)
        display(msg, self.sqs_response_queue, self.sqs_request_message)
        #call_callback_module('playbook_on_not_import_for_host', host, missing_file)

    def on_play_start(self, name):
        display(banner("PLAY [%s]" % name), self.sqs_response_queue, self.sqs_request_message)
        #call_callback_module('playbook_on_play_start', name)

    def on_stats(self, stats):
        pass
        #call_callback_module('playbook_on_stats', stats)