'use strict';
(() => {
    const form = document.getElementById('assignmentForm');
    if (!form) return;
    const lesson = form.elements.lesson, classroom = form.elements.classroom;
    const repetitions = form.elements.repetitions, vocabulary = document.getElementById('vocabularyRepetitions');
    const button = document.getElementById('assignButton'), preview = document.getElementById('assignmentPreview');
    const status = document.getElementById('assignmentPreviewStatus'), retry = document.getElementById('retryAssignmentPreview');
    let controller;
    function showVocabulary(skill) {
        const visible = skill === 'vocabulary';
        vocabulary.hidden = !visible;
        repetitions.disabled = !visible;
        repetitions.required = visible;
    }
    async function refresh() {
        controller?.abort();
        const active = new AbortController();
        controller = active;
        button.disabled = true;
        retry.hidden = true;
        showVocabulary('');
        status.textContent = 'Đang kiểm tra nội dung và lớp nhận bài…';
        const params = new URLSearchParams();
        if (lesson.value) params.set('lesson', lesson.value);
        if (classroom.value) params.set('classroom', classroom.value);
        try {
            const response = await fetch(form.dataset.previewUrl + '?' + params, {cache: 'no-store', signal: active.signal});
            if (response.status === 401) throw new Error('Phiên đăng nhập đã hết hạn. Đăng nhập lại để tiếp tục giao bài.');
            if (!response.ok) throw new Error('Chưa kiểm tra được nội dung. Hãy kiểm tra lại hoặc tải lại trang.');
            const data = await response.json();
            if (controller !== active) return;
            // This fragment is rendered by Django with autoescaping, never from user-provided HTML.
            preview.innerHTML = data.html;
            showVocabulary(data.skill);
            button.disabled = !data.ready;
            status.textContent = data.ready ? 'Đã kiểm tra nội dung và lớp nhận bài.' : 'Xem nội dung cần bổ sung bên dưới.';
        } catch (error) {
            if (error.name !== 'AbortError' && controller === active) {
                status.textContent = error.message;
                retry.hidden = false;
            }
        }
    }
    lesson.addEventListener('change', refresh);
    classroom.addEventListener('change', refresh);
    retry.addEventListener('click', refresh);
    window.addEventListener('pagehide', () => controller?.abort());
    showVocabulary(form.dataset.initialSkill);
    refresh();
})();
