from __future__ import absolute_import

from sentry import http
from sentry.utils import json


class RedmineClient(object):
    def __init__(self, host, key):
        self.host = host.rstrip('/')
        self.key = key

    def request(self, method, path, data=None, decode_response=True):
        headers = {
            'X-Redmine-API-Key': self.key,
            'Content-Type': "application/json",
        }
        url = '{}{}'.format(self.host, path)
        session = http.build_session()
        req = getattr(session, method.lower())(url, json=data, headers=headers)
        if decode_response:
            return json.loads(req.text)
        else:
            return req

    def get_projects(self):
        limit = 100
        projects = []

        def get_response(limit, offset):
            return self.request('GET', '/projects.json?limit=%s&offset=%s' % (limit, offset))

        response = get_response(limit, 0)

        while len(response['projects']):
            projects.extend(response['projects'])
            response = get_response(limit, response['offset'] + response['limit'])

        return {'projects': projects}

    def get_trackers(self):
        response = self.request('GET', '/trackers.json')
        return response

    def get_priorities(self):
        response = self.request('GET', '/enumerations/issue_priorities.json')
        return response

    def get_issue(self, issue_id):
        response = self.request('GET', '/issues/{}.json'.format(issue_id))
        return response['issue']

    def create_issue(self, data):
        response = self.request('POST', '/issues.json', data={
            'issue': data,
        })

        if 'issue' not in response or 'id' not in response['issue']:
            raise Exception('Unable to create redmine ticket')

        return response

    def add_comment(self, issue_id, comment):
        return self.request('PUT', '/issues/{}.json'.format(issue_id),
                            data={'issue': {'notes': comment}},
                            decode_response=False)
