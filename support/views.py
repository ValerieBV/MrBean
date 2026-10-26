from datetime import timedelta
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Q, Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from ai_core.models import GradingJob
from .forms import MessageForm, ContactForm
from .models import Conversation
from .permissions import conversations_for, is_student
from . import services


def private_render(request, template, context, status=200):
    response=render(request,template,context,status=status)
    response['Cache-Control']='private, no-store'
    return response


def learner_required(request):
    if not is_student(request.user):
        raise PermissionDenied


def own_job(request, pk):
    try:pk=int(pk)
    except (ValueError,TypeError):raise Http404
    return get_object_or_404(GradingJob.objects.select_related('task__learner','task__teacher',
        'task__assignment__classroom'),pk=pk,task__learner=request.user,status='graded')


@login_required
def thread_list(request, kind):
    rows=conversations_for(request.user).filter(kind=kind).annotate(message_count=Count('messages')).order_by('-updated_at','-pk')
    status=request.GET.get('status','')
    query=request.GET.get('q','').strip()[:100]
    if status in dict(Conversation.STATUS_CHOICES):rows=rows.filter(status=status)
    if query:rows=rows.filter(Q(subject__icontains=query)|Q(student__username__icontains=query)|Q(student__first_name__icontains=query))
    results=GradingJob.objects.filter(task__learner=request.user,status='graded').select_related('task').order_by('-submitted_at') if is_student(request.user) and kind==Conversation.KNOWLEDGE else []
    result_page=Paginator(results,10).get_page(request.GET.get('results_page'))
    return private_render(request,'support/list.html',{'threads':Paginator(rows,20).get_page(request.GET.get('page')),
        'kind':kind,'status_filter':status,'query':query,'statuses':[c for c in Conversation.STATUS_CHOICES
            if c[0]!='ai' or (kind==Conversation.KNOWLEDGE and is_student(request.user))],
        'is_learner':is_student(request.user),'results':result_page,'support_is_contact':kind==Conversation.CONTACT})


@login_required
def start(request, job_id):
    learner_required(request)
    job=own_job(request,job_id)
    existing=Conversation.objects.filter(student=request.user,job=job,kind=Conversation.KNOWLEDGE).first()
    if existing and request.method!='POST':return redirect(existing)
    form=MessageForm(request.POST or None)
    form.fields['body'].label='Bạn muốn được giải thích thêm điều gì?'
    if request.method=='POST' and form.is_valid():
        try:
            thread=services.start_study(request.user,job)
            services.learner_message(thread,request.user,form.cleaned_data['body'],form.cleaned_data['client_key'])
            return redirect(thread)
        except (ValidationError,IntegrityError) as exc:
            form.add_error(None,exc if isinstance(exc,ValidationError) else 'Có yêu cầu đang được gửi. Vui lòng tải lại cuộc trao đổi.')
    return private_render(request,'support/start.html',{'form':form,'job':job})


@login_required
def contact_new(request):
    learner_required(request)
    initial={}
    if request.GET.get('job'):
        job=own_job(request,request.GET['job'])
        initial.update(job=job.pk,subject=('Thắc mắc: '+job.task.title)[:180],category='grade')
        if job.task.assignment_id:
            initial['target']=f'teacher:{job.task.assignment.classroom_id}'
    form=ContactForm(request.POST or None,student=request.user,initial=initial)
    if request.method=='POST' and form.is_valid():
        try:
            thread=services.create_contact(request.user,**form.cleaned_data)
            messages.success(request,'Đã gửi liên hệ đến người phụ trách.')
            return redirect(thread)
        except (ValidationError,IntegrityError) as exc:
            form.add_error(None,exc if isinstance(exc,ValidationError) else 'Yêu cầu đang được gửi. Vui lòng kiểm tra danh sách liên hệ.')
    return private_render(request,'support/contact_form.html',{'form':form,'support_is_contact':True})


def detail_context(request,thread,form=None):
    rows=thread.messages.select_related('author')
    paginator=Paginator(rows,30)
    page=paginator.get_page(request.GET.get('page') or paginator.num_pages)
    last=thread.ai_attempts.select_related('question').first()
    expired=bool(last and last.status=='processing' and last.created_at<timezone.now()-timedelta(seconds=settings.AI_TUTOR_TIMEOUT_SECONDS+15))
    busy=bool(last and last.status=='processing' and not expired and thread.status==Conversation.AI)
    retry=bool(last and (last.status=='failed' or expired) and last.error_code!='daily_limit'
               and last.question.ai_attempts.count()<3 and thread.status==Conversation.AI)
    return {'thread':thread,'chat_messages':page,'form':form or MessageForm(),'is_learner':is_student(request.user),
            'support_is_contact':thread.kind==Conversation.CONTACT,
            'can_reply':thread.status!=Conversation.CLOSED and not busy and (is_student(request.user) or services.staff_can_reply(thread,request.user)),
            'can_escalate':is_student(request.user) and thread.kind==Conversation.KNOWLEDGE and not thread.escalated_at
                           and thread.status!=Conversation.CLOSED,
            'teacher_available':bool(services.teacher_for(thread)), 'last_attempt':last,
            'attempt_expired':expired,'can_retry':is_student(request.user) and retry}


@login_required
def detail(request, pk):
    thread=get_object_or_404(conversations_for(request.user),pk=pk)
    return private_render(request,'support/detail.html',detail_context(request,thread))


@login_required
@require_POST
def reply(request, pk):
    thread=get_object_or_404(conversations_for(request.user),pk=pk)
    form=MessageForm(request.POST)
    if form.is_valid():
        try:
            if is_student(request.user):
                services.learner_message(thread,request.user,**form.cleaned_data)
            else:
                services.staff_message(thread,request.user,**form.cleaned_data)
            return redirect(thread)
        except (ValidationError,IntegrityError) as exc:
            form.add_error(None,exc if isinstance(exc,ValidationError) else 'Một yêu cầu khác đang được xử lý. Hãy tải lại cuộc trao đổi.')
    thread.refresh_from_db()
    return private_render(request,'support/detail.html',detail_context(request,thread,form),status=400)


@login_required
@require_POST
def handoff(request, pk):
    learner_required(request)
    thread=get_object_or_404(conversations_for(request.user),pk=pk)
    try:
        services.escalate(thread,request.user,request.POST.get('note',''))
        messages.success(request,'Đã chuyển câu hỏi và lịch sử trao đổi đến giáo viên phụ trách.')
    except ValidationError as exc:messages.error(request,' '.join(exc.messages))
    return redirect(thread)


@login_required
@require_POST
def retry(request, pk):
    learner_required(request)
    thread=get_object_or_404(conversations_for(request.user),pk=pk)
    try:
        services.retry_question(thread,request.user,int(request.POST.get('question',0)))
    except (ValueError,ValidationError,IntegrityError) as exc:
        messages.error(request,' '.join(exc.messages) if isinstance(exc,ValidationError) else 'Không thể thử lại câu này. Vui lòng tải lại trang.')
    return redirect(thread)


@login_required
@require_POST
def close(request, pk):
    thread=get_object_or_404(conversations_for(request.user),pk=pk)
    services.set_closed(thread,request.user,closed=request.POST.get('action')!='reopen')
    return redirect(thread)
