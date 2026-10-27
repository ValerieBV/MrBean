from datetime import timedelta
from django.template.loader import get_template
from django.urls import reverse
from django.utils import timezone
from assignments.models import Lesson
from ai_core.services import enqueue_submission
from dashboard.testutils import IntegratedFixture


class BranchInterfaceIntegrationTests(IntegratedFixture):
    def test_all_fifteen_source_templates_compile(self):
        for name in ['assignments/assignment_list.html','assignments/confirm_delete.html',
                     'assignments/lesson_detail.html','assignments/lesson_form.html','assignments/skill_lessons.html',
                     'submissions/do_listening.html','submissions/do_speaking.html','submissions/do_vocab.html',
                     'submissions/student_dashboard.html','submissions/student_home.html','submissions/student_skill.html',
                     'admin/base_site.html','base_admin.html','base_student.html','registration/login.html']:
            with self.subTest(template=name):get_template(name)

    def test_bank_uses_source_cards_and_skill_table_with_real_data(self):
        self.client.force_login(self.teacher)
        response=self.client.get(reverse('assignments:assignment_list'))
        self.assertTemplateUsed(response,'assignments/assignment_list.html')
        self.assertEqual(len(response.context['cards']),3)
        response=self.client.get(reverse('assignments:skill_lessons',args=['listening']))
        self.assertTemplateUsed(response,'assignments/skill_lessons.html')
        self.assertContains(response,self.listening.title)
        self.assertNotContains(response,'data-pk="'+str(self.listening.pk)+'"')

    def test_source_bank_pagination_can_reach_lessons_after_first_page(self):
        Lesson.objects.bulk_create([Lesson(skill='vocabulary',program='B1',order=100+i,title=f'Extra lesson {i}') for i in range(23)])
        self.client.force_login(self.teacher)
        url=reverse('assignments:skill_lessons',args=['vocabulary'])
        response=self.client.get(url)
        self.assertContains(response,'aria-label="Chuyển trang"')
        self.assertEqual(len(response.context['lessons']),20)
        response=self.client.get(url,{'page':2})
        self.assertGreater(len(response.context['lessons']),0)

    def test_student_class_selection_uses_only_own_active_enrollments(self):
        self.client.force_login(self.student)
        response=self.client.get(reverse('submissions:student_dashboard'))
        self.assertEqual([c['code'] for c in response.context['classes']],[self.classroom.class_code])
        self.assertEqual(self.client.get(reverse('submissions:enter_class',args=[self.other_classroom.class_code])).status_code,404)
        self.assertRedirects(self.client.get(reverse('submissions:enter_class',args=[self.classroom.class_code])),reverse('submissions:student_home'))
        self.assertEqual(self.client.session['learning_class_id'],self.classroom.pk)

    def test_skill_cards_count_submitted_work_and_exclude_unassigned_bank(self):
        Lesson.objects.create(skill='vocabulary',program='B1',order=999,title='PRIVATE UNASSIGNED LESSON')
        enqueue_submission(task=self.listening_task,submission_key='source-card-complete',answers={str(self.q1.pk):'B'})
        self.client.force_login(self.student)
        response=self.client.get(reverse('submissions:student_home'))
        cards={c['skill']:c for c in response.context['cards']}
        self.assertEqual(cards['listening']['total'],1)
        self.assertEqual(cards['listening']['done'],1)
        self.assertEqual(cards['vocabulary']['total'],1)
        self.assertNotContains(response,'PRIVATE UNASSIGNED')

    def test_skill_rows_keep_own_result_and_submission_policy(self):
        self.client.force_login(self.student)
        response=self.client.get(reverse('submissions:student_skill',args=['speaking']))
        self.assertTemplateUsed(response,'submissions/student_skill.html')
        self.assertEqual([r['task'].pk for r in response.context['rows']],[self.task.pk])
        self.assertEqual(self.client.get(reverse('submissions:student_skill',args=['invalid'])).status_code,404)
        self.assertEqual(self.client.get(reverse('assignments:assignment_list')).status_code,403)

    def test_forged_class_session_cannot_expose_other_classes(self):
        self.client.force_login(self.student)
        session=self.client.session;session['learning_class_id']=self.other_classroom.pk;session.save()
        response=self.client.get(reverse('submissions:student_skill',args=['speaking']))
        self.assertEqual([r['task'].pk for r in response.context['rows']],[self.task.pk])

    def test_future_work_stays_hidden_in_source_skill_pages(self):
        self.task.assigned_at=timezone.now()+timedelta(days=1);self.task.save()
        self.client.force_login(self.student)
        response=self.client.get(reverse('submissions:student_skill',args=['speaking']))
        self.assertEqual(response.context['rows'],[])

    def test_source_exercise_templates_use_snapshots_and_validated_submit_js(self):
        self.client.force_login(self.student)
        for task,template in [(self.task,'do_speaking'),(self.listening_task,'do_listening'),(self.vocab_task,'do_vocab')]:
            response=self.client.get(reverse('submissions:do_task',args=[task.pk]))
            self.assertTemplateUsed(response,'submissions/'+template+'.html')
            self.assertContains(response,'name="reference_version"')
            self.assertContains(response,'submissions/submit.js')
            self.assertNotContains(response,'|safe')
        self.assertNotContains(response,'Đánh dấu hoàn thành')

    def test_source_lesson_form_keeps_invalid_data_and_video_fields(self):
        self.client.force_login(self.teacher)
        response=self.client.post(reverse('assignments:lesson_create'),{
            'skill':'speaking','program':'B1','order':'invalid','title':'Video chưa có lời mẫu',
            'youtube_url':'https://www.youtube.com/watch?v=abcdefghijk'})
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'Video chưa có lời mẫu')
        self.assertContains(response,'name="reference_transcript"')
        self.assertContains(response,'name="video_file"')
        self.assertFalse(Lesson.objects.filter(title='Video chưa có lời mẫu').exists())

    def test_teacher_and_manager_cannot_enter_learner_class_selection(self):
        for user in [self.teacher,self.manager,self.admin]:
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse('submissions:student_dashboard')).status_code,403)

    def test_source_assets_are_local_and_login_uses_real_authentication(self):
        response=self.client.get('/login/')
        self.assertContains(response,'learning/tailwind.css')
        self.assertNotContains(response,'cdn.tailwindcss.com')
        self.assertNotContains(response,'fonts.googleapis.com')
        self.student.set_password('TestPassword123!');self.student.is_active=False;self.student.save()
        response=self.client.post('/login/',{'username':self.student.username,'password':'TestPassword123!'})
        self.assertEqual(response.status_code,200)
        self.assertNotIn('_auth_user_id',self.client.session)

    def test_both_login_interfaces_preserve_safe_next_and_role_landing(self):
        for user in [self.student,self.teacher]:
            user.set_password('RolePassword123!');user.save()
            for url in ['/login/','/accounts/login/']:
                self.client.logout()
                response=self.client.post(url,{'username':user.username,'password':'RolePassword123!','next':'https://invalid.example/'})
                destination='submissions:student_dashboard' if user==self.student else 'dashboard:index'
                self.assertRedirects(response,reverse(destination))
        self.client.logout()
        response=self.client.post('/login/',{'username':self.student.username,'password':'RolePassword123!','next':'/accounts/profile/'})
        self.assertRedirects(response,'/accounts/profile/')
