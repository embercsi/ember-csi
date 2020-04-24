#!/usr/bin/env python
import json
import os
import sys
import urllib2

ERNO_NUMBER_ARGS = 1
ERNO_JOB_INFO = 2
ERNO_STATUS = 3

HEADERS = {'Authorization': 'token ' + os.environ['TOKEN'],
           'Content-Type': 'application/json',
           'User-Agent': 'Ember-CSI_CI'}


def get_job_url(repository, job_name, run_id):
    url = 'https://api.github.com/repos/%s/actions/runs/%s/jobs' % (repository,
                                                                    run_id)
    req = urllib2.Request(url, headers=HEADERS)
    response = urllib2.urlopen(req)
    result = json.loads(response.read())
    for job in result['jobs']:
        if job['name'] != job_name:
            continue
        return job['html_url'] + '?check_suite_focus=true'
    sys.stderr.write('Could not find the requested job')
    exit(ERNO_JOB_INFO)


def set_state(state, repository, job_name, target_url, commit_sha):
    url = 'https://api.github.com/repos/%s/statuses/%s' % (repository,
                                                           commit_sha)
    data = json.dumps({'context': job_name,
                       'state': state,
                       'target_url': target_url})

    req = urllib2.Request(url, data, HEADERS)
    error = None
    try:
        response = urllib2.urlopen(req)
        if response.code != 201:
            error = 'Status code is %s' % response.code
    except Exception as exc:
        error = str(exc)

    if error:
        sys.stderr.write('Error sending status change: %s\n' % error)
        exit(ERNO_STATUS)


if __name__ == '__main__':
    if len(sys.argv) != 6:
        sys.stderr.write('Wrong number of arguments:\n\t%s job_name run_id '
                         'state repository commit_sha\n' %
                         os.path.basename(sys.argv[0]))
        exit(ERNO_NUMBER_ARGS)

    __, job_name, run_id, state, repository, commit_sha = sys.argv

    # Convert gh-actions job status to old checks status
    state = state.lower()
    if state == 'cancelled':
        state = 'error'

    target_url = get_job_url(repository, job_name, run_id)
    set_state(state, repository, job_name, target_url, commit_sha)
