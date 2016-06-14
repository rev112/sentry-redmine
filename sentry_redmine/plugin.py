from __future__ import absolute_import
import json

from django import forms
from django.utils.translation import ugettext_lazy as _
from sentry.plugins.bases.issue import IssuePlugin
from sentry.utils.cache import cache
from sentry.utils.http import absolute_uri

from .client import RedmineClient
from .forms import RedmineOptionsForm, RedmineNewIssueForm


def _get_cache_key(issue_id):
    return "sentry_redmine_issue_status:{}".format(issue_id)


class RedminePlugin(IssuePlugin):
    author = 'Sentry'
    author_url = 'https://github.com/getsentry/sentry-redmine'
    version = '0.1.0'
    description = "Integrate Redmine issue tracking by linking a user account to a project."
    resource_links = [
        ('Bug Tracker', 'https://github.com/getsentry/sentry-redmine/issues'),
        ('Source', 'https://github.com/getsentry/sentry-redmine'),
    ]

    slug = 'redmine'
    title = _('Redmine')
    conf_title = 'Redmine'
    conf_key = 'redmine'
    project_conf_form = RedmineOptionsForm
    new_issue_form = RedmineNewIssueForm

    ISSUE_CACHE_TIMEOUT = 60

    def is_configured(self, project, **kwargs):
        return all((self.get_option(k, project) for k in ('host', 'key', 'project_id')))

    def get_new_issue_title(self, **kwargs):
        return 'Create Redmine Task'

    def get_initial_form_data(self, request, group, event, **kwargs):
        return {
            'description': self._get_group_description(request, group, event),
            'title': self._get_group_title(request, group, event),
        }

    def _get_group_description(self, request, group, event):
        output = [
            absolute_uri(group.get_absolute_url()),
        ]
        body = self._get_group_body(request, group, event)
        if body:
            output.extend([
                '',
                '<pre>',
                body,
                '</pre>',
            ])
        return '\n'.join(output)

    def get_client(self, project):
        return RedmineClient(
            host=self.get_option('host', project),
            key=self.get_option('key', project),
        )

    def create_issue(self, group, form_data, **kwargs):
        """
        Create a Redmine issue
        """
        client = self.get_client(group.project)

        if form_data.get('task_exists'):
            issue_id = form_data.get('existing_task_number')
            try:
                client.get_issue(issue_id)
            except Exception:
                raise forms.ValidationError('Cannot fetch the specified issue')
            else:
                return issue_id

        default_priority = self.get_option('default_priority', group.project)
        if default_priority is None:
            default_priority = 4

        issue_dict = {
            'project_id': self.get_option('project_id', group.project),
            'tracker_id': self.get_option('tracker_id', group.project),
            'priority_id': default_priority,
            'subject': form_data['title'].encode('utf-8'),
            'description': form_data['description'].encode('utf-8'),
        }

        extra_fields_str = self.get_option('extra_fields', group.project)
        if extra_fields_str:
            extra_fields = json.loads(extra_fields_str)
        else:
            extra_fields = {}
        issue_dict.update(extra_fields)

        response = client.create_issue(issue_dict)
        return response['issue']['id']

    def get_issue_url(self, group, issue_id, **kwargs):
        host = self.get_option('host', group.project)
        return '{}/issues/{}'.format(host.rstrip('/'), issue_id)

    def get_issue_label(self, group, issue_id, **kwargs):
        num_label = super(RedminePlugin, self).get_issue_label(group, issue_id,
                                                               **kwargs)
        # Try to read from the cache first
        issue_cache_key = _get_cache_key(issue_id)
        cached_value = cache.get(issue_cache_key)
        if cached_value is not None:
            return cached_value

        client = self.get_client(group.project)
        try:
            issue_data = client.get_issue(issue_id)
        except Exception:
            issue_label = '{} <unknown>'.format(num_label)
        else:
            issue_status = issue_data['issue']['status']
            issue_label = '{} ({})'.format(num_label, issue_status['name'])

        cache.set(issue_cache_key, issue_label, self.ISSUE_CACHE_TIMEOUT)
        return issue_label
