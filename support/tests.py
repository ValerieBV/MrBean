import json
import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone
from accounts.models import Notification
from ai_core.models import GradingJob
from dashboard.testutils import IntegratedFixture
from .ai import OpenAITutor, context_for
from .forms import ContactForm
from .models import Conversation, Message, TutorAttempt
from .permissions import conversations_for
from . import services


class SupportTests(IntegratedFixture):
    def setUp(self):
        super().setUp()
        self.job=GradingJob.objects.create(task=self.task,submission_key='support-grade',kind='speaking',status='graded',
            final_score=7.5,suggested_score=9.99,teacher_feedback='Ôn lại cấu trúc My hobby is reading.',
            transcript='My hobby reading.',rubric_snapshot=self.task.assignment.rubric,
            result={'score':9.99,'feedback':'PRIVATE MODEL FEEDBACK'})
        self.thread=services.start_study(self.student,self.job)
        self.provider=Mock()
        self.provider.answer.return_value={'answer':'Sau động từ be có thể dùng một cụm danh động từ. Ví dụ: My hobby is reading.', 'route':'knowledge'}

    def question(self,body='Vì sao dùng reading trong câu này?',key=None):
        return services.learner_message(self.thread,self.student,body,key or uuid.uuid4(),provider=self.provider)

    def contact(self,student=None,target=None,job=None,key=None):
        return services.create_contact(student or self.student,subject='Cần kiểm tra lịch học',category='schedule',
            target=target or f'management:{self.manager.pk}',job=job,body='Em muốn xác nhận lại lịch học tuần này.',client_key=key or uuid.uuid4())

    def test_start_requires_own_published_result(self):
        self.client.force_login(self.student)
        pending=GradingJob.objects.create(task=self.task,submission_key='pending-support',kind='speaking')
        self.assertEqual(self.client.get(reverse('support:start',args=[pending.pk])).status_code,404)
        self.client.force_login(self.other_student)
        self.assertEqual(self.client.get(reverse('support:start',args=[self.job.pk])).status_code,404)
        with self.assertRaises(PermissionDenied):services.start_study(self.other_student,self.job)
        with self.assertRaises(ValidationError):services.start_study(self.student,pending)

    def test_one_study_thread_per_result_and_get_does_not_create(self):
        self.assertEqual(services.start_study(self.student,self.job).pk,self.thread.pk)
        self.thread.delete()
        self.client.force_login(self.student)
        response=self.client.get(reverse('support:start',args=[self.job.pk]))
        self.assertEqual(response.status_code,200)
        self.assertFalse(Conversation.objects.exists())

    def test_ai_message_is_durable_and_duplicate_post_is_idempotent(self):
        key=uuid.uuid4();first=self.question(key=key);second=self.question(key=key)
        self.assertEqual(first.pk,second.pk)
        self.assertEqual(self.provider.answer.call_count,1)
        self.assertEqual(self.thread.messages.count(),2)
        self.assertEqual(self.thread.ai_attempts.get().status,'completed')
        self.assertFalse(Notification.objects.filter(event_key__startswith='support-').exists())

    def test_knowledge_and_ai_history_are_private_until_handoff(self):
        self.question()
        for user in [self.teacher,self.other_teacher,self.manager,self.admin,self.other_student]:
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.thread.get_absolute_url()).status_code,404)
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(self.thread.get_absolute_url()).status_code,200)

    def test_context_uses_only_published_result_and_no_private_ai_scores(self):
        context=context_for(self.thread)
        self.assertEqual(context['final_score'],7.5)
        self.assertEqual(context['teacher_feedback'],self.job.teacher_feedback)
        self.assertIn('My hobby',context['reference'])
        payload=json.dumps(context)
        self.assertNotIn('9.99',payload)
        self.assertNotIn('PRIVATE MODEL',payload)
        self.assertNotIn(self.other_student.username,payload)

    def test_unpublished_or_forged_context_is_rejected(self):
        self.job.status='ai_reviewed';self.job.save(update_fields=['status'])
        self.thread.refresh_from_db()
        with self.assertRaises(ValueError):context_for(self.thread)

    @override_settings(OPENAI_API_KEY='test-not-real',OPENAI_TUTOR_MODEL='gpt-6-luna')
    def test_openai_adapter_sends_scoped_context_and_recent_history(self):
        self.question()
        next_question=Message.objects.create(conversation=self.thread,author=self.student,role='student',body='Cho em thêm ví dụ khác.')
        with patch('openai.OpenAI') as factory:
            api=factory.return_value.__enter__.return_value
            api.responses.create.return_value=SimpleNamespace(output_text=json.dumps({'answer':'My hobby is swimming.','route':'knowledge'}))
            answer=OpenAITutor().answer(self.thread,next_question)
            kwargs=api.responses.create.call_args.kwargs
            self.assertEqual(answer['answer'],'My hobby is swimming.')
            self.assertFalse(kwargs['store'])
            self.assertEqual(factory.call_args.kwargs['max_retries'],0)
            self.assertEqual(kwargs['input'][-1]['content'],next_question.body)
            self.assertEqual(kwargs['input'][-2]['role'],'assistant')
            self.assertNotIn('9.99',json.dumps(kwargs))
            self.assertNotIn('test-not-real',json.dumps(kwargs['input']))

    def test_provider_failure_preserves_question_without_fake_answer(self):
        self.provider.answer.side_effect=RuntimeError('SECRET TOKEN must not appear')
        self.question()
        self.assertEqual(self.thread.messages.filter(role='student').count(),1)
        self.assertFalse(self.thread.messages.filter(role='assistant').exists())
        self.assertEqual(self.thread.ai_attempts.get().status,'failed')
        self.client.force_login(self.student)
        response=self.client.get(self.thread.get_absolute_url())
        self.assertContains(response,'Câu hỏi đã được lưu')
        self.assertContains(response,'Hỏi giáo viên')
        self.assertNotContains(response,'SECRET TOKEN')

    def test_invalid_ai_output_is_not_published(self):
        for data in [{'answer':'','route':'knowledge'},{'answer':'x'*6001,'route':'knowledge'},{'answer':'text','route':'delete_grade'}]:
            self.provider.answer.return_value=data
            self.question()
        self.assertEqual(self.thread.messages.filter(role='assistant').count(),0)
        self.assertEqual(self.thread.ai_attempts.filter(status='failed').count(),3)

    @override_settings(AI_TUTOR_DAILY_LIMIT=1)
    def test_daily_budget_does_not_block_teacher_handoff(self):
        self.question();self.question('Em muốn thêm một ví dụ khác.')
        self.assertEqual(self.provider.answer.call_count,1)
        self.assertEqual(self.thread.ai_attempts.first().error_code,'daily_limit')
        services.escalate(self.thread,self.student)
        self.thread.refresh_from_db()
        self.assertEqual(self.thread.status,Conversation.WAITING)

    def test_failed_question_can_retry_with_a_three_attempt_cap(self):
        self.provider.answer.side_effect=RuntimeError('unavailable')
        question=self.question()
        for _ in range(2):services.retry_question(self.thread,self.student,question.pk,provider=self.provider)
        with self.assertRaises(ValidationError):services.retry_question(self.thread,self.student,question.pk,provider=self.provider)
        self.assertEqual(self.provider.answer.call_count,3)

    def test_completed_question_is_not_billed_again(self):
        question=self.question()
        with self.assertRaises(ValidationError):services.retry_question(self.thread,self.student,question.pk,provider=self.provider)
        self.assertEqual(self.provider.answer.call_count,1)

    def test_abandoned_request_can_be_retried_and_old_result_cannot_overwrite(self):
        question=Message.objects.create(conversation=self.thread,author=self.student,role='student',body='Câu hỏi chưa được xử lý.')
        old=TutorAttempt.objects.create(conversation=self.thread,question=question,status='processing')
        TutorAttempt.objects.filter(pk=old.pk).update(created_at=timezone.now()-timedelta(minutes=2))
        services.retry_question(self.thread,self.student,question.pk,provider=self.provider)
        old.refresh_from_db();self.assertEqual(old.status,'failed')
        services.run_attempt(old,provider=self.provider)
        self.assertEqual(self.provider.answer.call_count,1)
        self.assertEqual(self.thread.messages.filter(role='assistant').count(),1)

    def test_fresh_inflight_request_blocks_second_ai_request(self):
        question=Message.objects.create(conversation=self.thread,author=self.student,role='student',body='Câu đang gửi.')
        TutorAttempt.objects.create(conversation=self.thread,question=question,status='processing')
        with self.assertRaises(ValidationError):self.question()
        self.assertFalse(self.provider.answer.called)
        self.assertEqual(self.thread.messages.count(),1)

    def test_handoff_transfers_history_notifies_once_and_routes_followups_to_teacher(self):
        self.question();services.escalate(self.thread,self.student,'Em vẫn cần thầy giải thích thêm.')
        services.escalate(self.thread,self.student)
        self.thread.refresh_from_db()
        self.assertEqual(self.thread.recipient,self.teacher)
        self.assertEqual(Notification.objects.filter(event_key=f'support-escalation:{self.thread.pk}').count(),1)
        for user,expected in [(self.teacher,200),(self.admin,200),(self.manager,404),(self.other_teacher,404),(self.other_student,404)]:
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.thread.get_absolute_url()).status_code,expected)
        services.staff_message(self.thread,self.teacher,'Reading ở đây đóng vai trò danh động từ.',uuid.uuid4())
        self.thread.refresh_from_db();self.assertEqual(self.thread.status,Conversation.ANSWERED)
        self.question('Em đã hiểu hơn, xin thầy thêm một ví dụ.')
        self.assertEqual(self.provider.answer.call_count,1)
        self.thread.refresh_from_db();self.assertEqual(self.thread.status,Conversation.WAITING)
        self.assertTrue(self.student.notifications.filter(event_key__startswith='support-message:').exists())

    def test_late_ai_answer_is_discarded_after_handoff(self):
        def answer(thread,question):
            services.escalate(thread,self.student)
            return {'answer':'Late AI answer','route':'knowledge'}
        self.provider.answer.side_effect=answer
        self.question()
        self.assertFalse(self.thread.messages.filter(role='assistant').exists())
        self.assertEqual(self.thread.ai_attempts.get().status,'cancelled')

    def test_missing_teacher_keeps_question_and_offers_management_contact(self):
        self.classroom.teacher=None;self.classroom.save()
        self.question()
        with self.assertRaises(ValidationError):services.escalate(self.thread,self.student)
        self.client.force_login(self.student)
        self.assertContains(self.client.get(self.thread.get_absolute_url()),'liên hệ đến quản lý')

    def test_transfer_removes_old_teacher_and_assigns_new_teacher(self):
        self.question();services.escalate(self.thread,self.student)
        self.classroom.teacher=self.other_teacher;self.classroom.save()
        self.thread.refresh_from_db();self.assertEqual(self.thread.recipient,self.other_teacher)
        self.assertFalse(conversations_for(self.teacher).filter(pk=self.thread.pk).exists())
        self.assertTrue(conversations_for(self.other_teacher).filter(pk=self.thread.pk).exists())

    def test_stale_assignment_never_grants_old_teacher_access(self):
        self.question();services.escalate(self.thread,self.student)
        from courses.models import ClassRoom
        ClassRoom.objects.filter(pk=self.classroom.pk).update(teacher=self.other_teacher)
        self.assertFalse(conversations_for(self.teacher).filter(pk=self.thread.pk).exists())
        with self.assertRaises(PermissionDenied):
            services.staff_message(self.thread,self.teacher,'Không được trả lời sau khi đổi phụ trách.',uuid.uuid4())

    def test_contacts_never_call_ai_and_restrict_inbox_to_recipient(self):
        with patch('support.services.OpenAITutor') as api:
            contact=self.contact()
            services.learner_message(contact,self.student,'Em muốn bổ sung thời gian có thể học.',uuid.uuid4())
            services.staff_message(contact,self.manager,'Trung tâm sẽ xác nhận lại lịch học.',uuid.uuid4())
            api.assert_not_called()
        self.assertFalse(contact.ai_attempts.exists())
        self.assertTrue(conversations_for(self.manager).filter(pk=contact.pk).exists())
        for user in [self.teacher,self.other_student]:
            self.assertFalse(conversations_for(user).filter(pk=contact.pk).exists())

    def test_duplicate_contact_and_staff_reply_do_not_duplicate_notifications(self):
        key=uuid.uuid4();first=self.contact(key=key);second=self.contact(key=key)
        self.assertEqual(first.pk,second.pk);self.assertEqual(first.messages.count(),1)
        key=uuid.uuid4()
        a=services.staff_message(first,self.manager,'Đã ghi nhận nội dung liên hệ.',key)
        b=services.staff_message(first,self.manager,'Đã ghi nhận nội dung liên hệ.',key)
        self.assertEqual(a.pk,b.pk)
        self.assertEqual(Notification.objects.filter(event_key=f'support-message:{a.pk}').count(),1)

    def test_changed_contact_with_reused_nonce_is_not_silently_discarded(self):
        key=uuid.uuid4();self.contact(key=key)
        with self.assertRaises(ValidationError):
            services.create_contact(self.student,subject='Nội dung đã chỉnh sửa',category='schedule',
                target=f'management:{self.manager.pk}',job=None,body='Em muốn thay nội dung phản ánh.',client_key=key)
        self.assertEqual(Conversation.objects.filter(kind='contact').count(),1)

    def test_recipient_forgery_and_other_students_result_are_rejected(self):
        with self.assertRaises(ValidationError):self.contact(target=f'teacher:{self.other_classroom.pk}')
        with self.assertRaises(PermissionDenied):self.contact(student=self.other_student,job=self.job)
        self.assertNotIn(f'teacher:{self.other_classroom.pk}',dict(ContactForm(student=self.student).fields['target'].choices))
        with self.assertRaises(PermissionDenied):services.staff_message(self.thread,self.manager,'Unauthorized response',uuid.uuid4())

    def test_teacher_contact_requires_matching_result_class(self):
        # An historical enrollment can offer a teacher as a contact, but it must
        # not attach another class's result to that teacher's conversation.
        from courses.models import Enrollment
        Enrollment.objects.create(classroom=self.other_classroom,student=self.student,status='completed')
        with self.assertRaises(ValidationError):self.contact(target=f'teacher:{self.other_classroom.pk}',job=self.job)

    def test_closure_and_reopen_preserve_human_route_and_history(self):
        self.question();services.escalate(self.thread,self.student)
        services.set_closed(self.thread,self.student,True)
        with self.assertRaises(ValidationError):self.question('Em muốn hỏi tiếp câu này.')
        services.set_closed(self.thread,self.student,False)
        self.thread.refresh_from_db();self.assertEqual(self.thread.status,Conversation.WAITING)
        self.assertEqual(self.thread.recipient,self.teacher)
        self.question('Em muốn hỏi tiếp câu này.')
        self.assertEqual(self.provider.answer.call_count,1)

    def test_pages_escape_messages_and_paginate_history(self):
        self.question('<script>alert("test")</script>')
        for i in range(35):Message.objects.create(conversation=self.thread,role='system',body=f'History line {i}')
        self.client.force_login(self.student)
        response=self.client.get(self.thread.get_absolute_url()+'?page=1')
        self.assertContains(response,'&lt;script&gt;')
        self.assertNotContains(response,'<script>alert(')
        self.assertEqual(len(response.context['chat_messages']),30)
        self.assertEqual(response['Cache-Control'],'private, no-store')

    def test_contacts_can_be_created_and_replied_through_views(self):
        self.client.force_login(self.student)
        response=self.client.post(reverse('support:contact_new'),{'subject':'Lỗi khi mở video','category':'technical',
            'target':f'management:{self.manager.pk}','body':'Em không mở được video của buổi học.','client_key':str(uuid.uuid4())})
        self.assertEqual(response.status_code,302)
        contact=Conversation.objects.get(kind=Conversation.CONTACT)
        self.client.force_login(self.manager)
        response=self.client.post(reverse('support:reply',args=[contact.pk]),{'body':'Em thử tải lại trình duyệt giúp thầy nhé.','client_key':str(uuid.uuid4())})
        self.assertRedirects(response,contact.get_absolute_url())
        contact.refresh_from_db();self.assertEqual(contact.status,Conversation.ANSWERED)

    def test_start_view_saves_question_and_follows_existing_thread(self):
        self.thread.delete()
        self.client.force_login(self.student)
        with patch('support.services.OpenAITutor') as provider:
            provider.return_value.answer.return_value={'answer':'Đây là một danh động từ.','route':'knowledge'}
            response=self.client.post(reverse('support:start',args=[self.job.pk]),{'body':'Vì sao dùng reading ở đây?','client_key':str(uuid.uuid4())})
        thread=Conversation.objects.get(kind=Conversation.KNOWLEDGE)
        self.assertRedirects(response,thread.get_absolute_url())
        self.assertEqual(thread.messages.count(),2)
        self.assertRedirects(self.client.get(reverse('support:start',args=[self.job.pk])),thread.get_absolute_url())

    def test_question_from_an_already_open_start_form_is_not_lost(self):
        self.client.force_login(self.student)
        with patch('support.services.OpenAITutor') as provider:
            provider.return_value.answer.return_value={'answer':'Đây là một danh động từ.','route':'knowledge'}
            response=self.client.post(reverse('support:start',args=[self.job.pk]),{
                'body':'Câu hỏi từ cửa sổ đã mở trước đó.','client_key':str(uuid.uuid4())})
        self.assertRedirects(response,self.thread.get_absolute_url())
        self.assertEqual(self.thread.messages.filter(role='student').count(),1)

    def test_mutations_require_post_and_csrf(self):
        self.client.force_login(self.student)
        for name in ['reply','handoff','retry','close']:
            self.assertEqual(self.client.get(reverse('support:'+name,args=[self.thread.pk])).status_code,405)
        strict=Client(enforce_csrf_checks=True);strict.force_login(self.student)
        self.assertEqual(strict.post(reverse('support:handoff',args=[self.thread.pk])).status_code,403)

    def test_invalid_forms_keep_content_and_do_not_create_messages(self):
        self.client.force_login(self.student)
        response=self.client.post(reverse('support:reply',args=[self.thread.pk]),{'body':'A','client_key':str(uuid.uuid4())})
        self.assertEqual(response.status_code,400)
        self.assertContains(response,'value=',status_code=400)
        self.assertEqual(self.thread.messages.count(),0)
        self.assertEqual(self.client.get(reverse('support:contact_new')+'?job=invalid').status_code,404)

    def test_only_student_owns_study_and_contact_creation(self):
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse('support:contact_new')).status_code,403)
        self.assertEqual(self.client.get(reverse('support:start',args=[self.job.pk])).status_code,403)

    def test_staff_inboxes_render_and_student_uses_results_for_knowledge(self):
        self.client.force_login(self.student)
        self.assertRedirects(self.client.get(reverse('support:knowledge_list')),reverse('submissions:student_home'))
        self.assertEqual(self.client.get(reverse('support:contact_list')).status_code,200)
        for user in [self.teacher,self.manager,self.admin]:
            self.client.force_login(user)
            for name in ['knowledge_list','contact_list']:
                self.assertEqual(self.client.get(reverse('support:'+name)).status_code,200)

    def test_contact_filters_and_summary_are_scoped_to_the_recipient(self):
        own=self.contact()
        services.staff_message(own,self.manager,'Trung tâm đã ghi nhận lịch học.',uuid.uuid4())
        self.contact(target=f'teacher:{self.classroom.pk}')
        self.client.force_login(self.manager)
        response=self.client.get(reverse('support:contact_list'),{'status':'waiting'})
        self.assertEqual(response.context['summary'],{'total':1,'waiting':0,'answered':1,'closed':0})
        self.assertEqual(response.context['threads'].paginator.count,0)
        response=self.client.get(reverse('support:contact_list'),{'q':'kiểm tra lịch','status':'answered'})
        self.assertEqual(list(response.context['threads']),[own])

    def test_student_contact_inbox_has_no_link_to_global_ai_chat(self):
        self.client.force_login(self.student)
        response=self.client.get(reverse('support:contact_list'))
        self.assertContains(response,'Tạo liên hệ mới')
        self.assertNotContains(response,'href="'+reverse('support:knowledge_list')+'"')
        response=self.client.get(self.thread.get_absolute_url())
        self.assertContains(response,'href="'+reverse('submissions:result',args=[self.job.pk])+'">Quay lại kết quả bài tập')

    def test_teacher_opens_escalated_questions_from_contact_inbox(self):
        self.question();services.escalate(self.thread,self.student)
        self.client.force_login(self.teacher)
        response=self.client.get(reverse('support:contact_list'))
        self.assertContains(response,'Câu hỏi từ bài tập')
        response=self.client.get(reverse('support:knowledge_list'))
        self.assertContains(response,self.thread.subject)
        self.assertEqual(response.context['summary']['waiting'],1)

    def test_missing_support_tables_show_role_appropriate_page_and_recover(self):
        for user in [self.student,self.teacher,self.manager,self.admin]:
            self.client.force_login(user)
            with patch('support.readiness.support_schema_ready',return_value=False):
                response=self.client.get(reverse('support:contact_list'))
            self.assertContains(response,'CHỨC NĂNG HỖ TRỢ ĐANG ĐƯỢC CẬP NHẬT',status_code=503)
            self.assertEqual(response['Cache-Control'],'private, no-store')
            self.assertEqual(response['Retry-After'],'60')
            if user==self.admin:self.assertContains(response,'python manage.py migrate',status_code=503)
            else:self.assertNotContains(response,'manage.py',status_code=503)
            # No cached failure: after migration the very next request works.
            self.assertEqual(self.client.get(reverse('support:contact_list')).status_code,200)

    def test_missing_tables_block_all_contact_writes_without_false_success(self):
        self.client.force_login(self.student)
        before=Conversation.objects.count()
        with patch('support.readiness.support_schema_ready',return_value=False), patch('support.services.OpenAITutor') as api:
            for name,kwargs in [('contact_new',{}),('start',{'job_id':self.job.pk}),
                                ('reply',{'pk':self.thread.pk}),('handoff',{'pk':self.thread.pk}),
                                ('retry',{'pk':self.thread.pk}),('close',{'pk':self.thread.pk})]:
                response=self.client.post(reverse('support:'+name,kwargs=kwargs),{'body':'Nội dung cần được giữ lại.'})
                self.assertContains(response,'Nội dung vừa gửi chưa được lưu',status_code=503)
            api.assert_not_called()
        self.assertEqual(Conversation.objects.count(),before)
        self.assertFalse(Message.objects.exists())

    def test_contact_form_explains_when_no_recipient_is_available(self):
        from accounts.models import CustomUser
        CustomUser.objects.exclude(pk=self.student.pk).update(is_active=False)
        self.client.force_login(self.student)
        response=self.client.get(reverse('support:contact_new'))
        self.assertContains(response,'Hiện chưa có giáo viên hoặc quản lý hoạt động')
        self.assertEqual(len(response.context['form'].fields['target'].choices),1)

    def test_django_admin_cannot_bypass_private_ai_history(self):
        self.admin.is_superuser=True;self.admin.save()
        request=RequestFactory().get('/admin/');request.user=self.admin
        model_admin=admin.site._registry[Conversation]
        self.assertFalse(model_admin.get_queryset(request).filter(pk=self.thread.pk).exists())
        self.question();services.escalate(self.thread,self.student)
        self.assertTrue(model_admin.get_queryset(request).filter(pk=self.thread.pk).exists())

    def test_message_admin_cannot_read_unescalated_messages(self):
        self.question();self.admin.is_superuser=True;self.admin.save()
        request=RequestFactory().get('/admin/');request.user=self.admin
        self.assertEqual(admin.site._registry[Message].get_queryset(request).filter(conversation=self.thread).count(),0)
