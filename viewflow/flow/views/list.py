from django.views import generic
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.utils.translation import ugettext_lazy as _
from django_filters import FilterSet, ChoiceFilter, DateRangeFilter, ModelChoiceFilter

from ... import activation, models
from ...fields import import_task_by_ref
from .mixins import LoginRequiredMixin, FlowViewPermissionMixin
from .utils import flows_start_actions, flow_start_actions


class TaskFilter(FilterSet):
    flow_task = ChoiceFilter(help_text='')
    created = DateRangeFilter(help_text='')
    process = ModelChoiceFilter(queryset=models.Process.objects.all(), help_text='')

    def __init__(self, data=None, queryset=None, prefix=None, strict=None):
        super(TaskFilter, self).__init__(data=data, queryset=queryset, prefix=prefix, strict=strict)
        self.filters['process'].field.queryset = \
            models.Process.objects.filter(id__in=queryset.values_list('process', flat=True))

        def task_name(task_ref):
            flow_task = import_task_by_ref(task_ref)
            return "{}/{}".format(flow_task.flow_cls.process_title, flow_task.name.title())

        tasks = [(task_ref, task_name(task_ref))
                 for task_ref in queryset.order_by('flow_task').distinct().values_list('flow_task', flat=True)]

        self.filters['flow_task'].field.choices = [(None, 'All')] + tasks

    class Meta:
        fields = ['process', 'flow_task', 'created']
        model = models.Task


class AllProcessListView(LoginRequiredMixin, generic.ListView):

    """All process instances list available for current user."""

    flows = []

    paginate_by = 15
    paginate_orphans = 5
    context_object_name = 'process_list'

    def get_template_names(self):
        return 'viewflow/site_index.html'

    def get_context_data(self, **kwargs):
        context = super(AllProcessListView, self).get_context_data(**kwargs)
        context['start_actions'] = flows_start_actions(self.flows, self.request.user)
        return context

    def get_queryset(self):
        return models.Process.objects \
            .filter_available(self.flows.values(), self.request.user) \
            .order_by('-created')


class AllTaskListView(generic.ListView):

    """All tasks from all processes assigned to current user."""

    flows = []

    paginate_by = 15
    paginate_orphans = 5
    context_object_name = 'task_list'

    def get_template_names(self):
        return 'viewflow/site_tasks.html'

    def get_context_data(self, **kwargs):
        context = super(AllTaskListView, self).get_context_data(**kwargs)
        context['start_actions'] = flows_start_actions(self.flows, self.request.user)
        context['filter'] = self.filter
        return context

    def get_queryset(self):
        return self.filter.qs

    def get_base_queryset(self, user):
        return models.Task.objects.inbox(self.flows.values(), user).order_by('-created')

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.filter = TaskFilter(request.GET, self.get_base_queryset(request.user))
        return super(AllTaskListView, self).dispatch(request, *args, **kwargs)


class AllQueueListView(generic.ListView):

    """All unassigned tasks available for current user."""

    flows = []

    paginate_by = 15
    paginate_orphans = 5
    context_object_name = 'queue'

    def get_template_names(self):
        return 'viewflow/site_queue.html'

    def get_context_data(self, **kwargs):
        context = super(AllQueueListView, self).get_context_data(**kwargs)
        context['start_actions'] = flows_start_actions(self.flows, self.request.user)
        context['filter'] = self.filter
        return context

    def get_queryset(self):
        return self.filter.qs

    def get_base_queryset(self, user):
        return models.Task.objects.queue(self.flows.values(), user).order_by('-created')

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.filter = TaskFilter(request.GET, self.get_base_queryset(request.user))
        return super(AllQueueListView, self).dispatch(request, *args, **kwargs)


class AllArchiveListView(LoginRequiredMixin, generic.ListView):

    """All tasks from all processes assigned to current user."""

    flows = {}

    paginate_by = 15
    paginate_orphans = 5
    context_object_name = 'task_list'

    def get_template_names(self):
        return 'viewflow/site_archive.html'

    def get_context_data(self, **kwargs):
        context = super(AllArchiveListView, self).get_context_data(**kwargs)
        context['start_actions'] = flows_start_actions(self.flows, self.request.user)
        return context

    def get_queryset(self):
        return models.Task.objects.archive(self.flows.values(), self.request.user).order_by('-created')


class ProcessFilter(FilterSet):
    status = ChoiceFilter(help_text='', choices=(
        (None, _('All')),
        (activation.STATUS.NEW, _('Active')),
        (activation.STATUS.CANCELED, _('Canceled')),
        (activation.STATUS.DONE, _('Completed')),
    ))
    created = DateRangeFilter(help_text='')
    finished = DateRangeFilter(help_text='')


class ProcessListView(FlowViewPermissionMixin, generic.ListView):
    paginate_by = 15
    paginate_orphans = 5
    context_object_name = 'process_list'

    def get_template_names(self):
        opts = self.flow_cls._meta

        return (
            '{}/{}/process_list.html'.format(opts.app_label, opts.flow_label),
            'viewflow/flow/process_list.html')

    def get_context_data(self, **kwargs):
        context = super(ProcessListView, self).get_context_data(**kwargs)
        context['start_actions'] = flow_start_actions(
            self.flow_cls, namespace=self.request.resolver_match.namespace, user=self.request.user)
        context['flow_cls'] = self.flow_cls
        return context

    def get_queryset(self):
        return self.filter.qs

    def get_base_queryset(self, user):
        return self.flow_cls.process_cls.objects \
            .filter(flow_cls=self.flow_cls) \
            .order_by('-created')

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.flow_cls = kwargs.get('flow_cls', self.flow_cls)
        self.filter = ProcessFilter(request.GET, self.get_base_queryset(request.user))
        return super(ProcessListView, self).dispatch(request, *args, **kwargs)


class TaskListView(FlowViewPermissionMixin, generic.ListView):

    """List of specific Flow tasks assigned to current user."""

    paginate_by = 15
    paginate_orphans = 5
    context_object_name = 'task_list'

    def get_template_names(self):
        opts = self.flow_cls._meta

        return (
            '{}/{}/task_list.html'.format(opts.app_label, opts.flow_label),
            'viewflow/flow/task_list.html')

    def get_context_data(self, **kwargs):
        context = super(TaskListView, self).get_context_data(**kwargs)
        context['start_actions'] = flow_start_actions(
            self.flow_cls, namespace=self.request.resolver_match.namespace, user=self.request.user)
        context['flow_cls'] = self.flow_cls
        return context

    def get_queryset(self):
        return self.flow_cls.task_cls.objects \
            .filter(process__flow_cls=self.flow_cls,
                    owner=self.request.user,
                    status=activation.STATUS.ASSIGNED) \
            .order_by('-created')


class QueueListView(FlowViewPermissionMixin, generic.ListView):

    """List of specific Flow unassigned tasks available for current user."""

    paginate_by = 15
    paginate_orphans = 5
    context_object_name = 'queue'

    def get_template_names(self):
        opts = self.flow_cls._meta

        return (
            '{}/{}/queue.html'.format(opts.app_label, opts.flow_label),
            'viewflow/flow/queue.html')

    def get_context_data(self, **kwargs):
        context = super(QueueListView, self).get_context_data(**kwargs)
        context['start_actions'] = flow_start_actions(
            self.flow_cls, namespace=self.request.resolver_match.namespace, user=self.request.user)
        context['flow_cls'] = self.flow_cls
        return context

    def get_queryset(self):
        queryset = self.flow_cls.task_cls.objects.user_queue(self.request.user, flow_cls=self.flow_cls) \
            .filter(status=activation.STATUS.NEW).order_by('-created')

        return queryset
