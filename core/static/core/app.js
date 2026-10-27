'use strict';

// Navigation is shared by all page shells through navigation.js.
for (const box of document.querySelectorAll('.table-responsive,.table-wrap,.report-scroll')) {
    box.setAttribute('role', 'region');
    box.setAttribute('aria-label', 'Bảng dữ liệu, có thể cuộn ngang');
    const update = () => {
        if (box.scrollWidth > box.clientWidth + 1) box.setAttribute('tabindex', '0');
        else box.removeAttribute('tabindex');
    };
    new ResizeObserver(update).observe(box);
    update();
}
const skillSelect = document.getElementById('id_skill');
if (skillSelect) {
    const toggleFields = () => {
        const fields = {listening_type:'listening', audio_file:'listening', video_file:'speaking',
            youtube_url:'speaking', reference_transcript:'speaking'};
        for (const [name, skill] of Object.entries(fields)) {
            const box = document.querySelector('[data-field="' + name + '"]');
            if (box) box.hidden = skillSelect.value !== skill && !box.dataset.hasErrors;
        }
    };
    skillSelect.addEventListener('change', toggleFields);
    toggleFields();
}
