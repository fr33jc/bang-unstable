SQS Listener
============

Overview
--------
The SQS Listener utilizes Amazon's Simple Queue Service (SQS) to request jobs to be
kicked off by Bang! and to log responses on a response queue.

Required Configuration files
----------------------------
The following files are required in order for the sqs-listener to work properly:
    -   '.sqslistener': This is the primary configuration file that contains information
        about the rest of your configuration files, specifically as a path to each of them.
        This, by default goes in ~/.sqslistener, but the path to the file can be modified
        in the /etc/default/bang-dispatcher file as described below.
    -   jobs.yml: This file contains information for a particular job, specifically what
        bang stacks to use in provisioning. See below for an example.
    -   logging-conf.yml: A standard python logging yaml file. See below for an example.


An example of a .sqslistener configuration file: (YAML)
::
    ---
    aws_region: us-east-1
    job_queue_name: bang-queue
    response_queue_name: bang-response
    polling_interval: 2  # in seconds.
    jobs_config_path: /root/sqslistener/jobs.yml
    logging_config_path: /root/sqslistener/logging-conf.yml


An example of a jobs config file such as the one specified above as /root/sqslistener/jobs.yml:
::
    ---
    test_job_1:
      bang-stacks:
       - /this/is/just/a/test.yml
    test_job_2:
      bang-stacks:
       - /this/is/just/a/test2.yml
       - /this/is/just/another/test2.yml
    test_job_3:
      bang-stacks:
       - /this/is/just/a/test3.yml


An example of a logging-conf.yml file:
::
    ---
    version: 1
    formatters:
      default:
        format: '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    handlers:
      file:
        class: logging.FileHandler
        level: DEBUG
        formatter: default
        filename: /root/sqslistener/logs/sqslistener.log
    loggers:
      SQSListener:
        level: DEBUG
        handlers: [file]
        propagate: no


Configuring the Init Script
---------------------------
On your Linux system, you will have an init script in /etc/init.d/sqs-listener. If you installed
bang with a virtualenv, you will need to modify the BANG_DISPATCHER variable either in the
preferred way of adding it to the /etc/default/bang-dispatcher shell script that is sourced
by the sqs-listener init script, or by modifying it in the init script itself.

Also helpful for the init script is to add the location of your primary sqs-listener configuration
file to /etc/default/bang-dispatcher. (If one is not provided, it defaults to ~/.sqslistener.)

Example of a /etc/default/bang-dispatcher file:
::
    BANG_DISPATCHER=/path/to/bang/venv/bin/bang-dispatcher
    CONFIG_PATH="/path/to/sqslistener/configuration/.sqslistener"


Example of a Request Message
----------------------------
The SQSListener consumes messages with a message body of yaml format from the request-queue
and kicks of bang messages based on them. Once a job is complete (whether a success or a
failure) a message is placed on the response queue for use by another application.

Below is an example of a request message to kick off a job:
::
    ---
    test_job_1:  # Job name (This is the same as the name defined in the jobs config.)
      request_id: 7f23b8ae-3e06-405c-9131-f133aaa12c96  # Unique Id
      parameters:
      - param1
      - param2
      - param3


Example of a Response Message
-----------------------------
The SQS Listener puts a response message in yaml format onto the response queue
specified in the .sqslistener config file. An example follows:
::
    ---
    job_name: test_job_1
    request_id: 7f23b8ae-3e06-405c-9131-f133aaa12c96
    result: success
    message: |-
      Everything was A-OK


The job_name will be the same as the name you gave in the request message.
The request_id will be the same as the request_id given in the request message as well.
The result can be any single-line string.
The message can any multi-line string.

The 'result' property in these messages will either be 'started', 'working', 'success',
or 'failure'.
    -   'started' means that the message has been received from the request queue and is
        being processed..
    -   'working' is a result status that accompanies intermediate update, such as log
        messages from bang/ansible.
    -   'success' means that the message ran the desired job and completed successfully.
    -   and 'failure' means that the message was either unable to run the desired job,
        or there was a problem with it.

In each of these cases, the 'message' property contains a multi-line message that describes in more detail,
information about what happened.
