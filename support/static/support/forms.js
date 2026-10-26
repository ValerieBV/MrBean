'use strict';
for (const form of document.querySelectorAll('[data-support-form]')) {
    form.addEventListener('submit', event => {
        if (form.dataset.sending) { event.preventDefault(); return; }
        form.dataset.sending = 'true';
        const button = event.submitter || form.querySelector('[type=submit]');
        if (button) { button.disabled = true; button.textContent = button.dataset.waitingLabel || 'Đang gửi…'; }
        const status = form.querySelector('[data-support-status]');
        if (status) status.textContent = 'Đang xử lý yêu cầu. Vui lòng chờ phản hồi.';
    });
}
window.addEventListener('pageshow', event => {
    if (event.persisted) location.reload();
});
