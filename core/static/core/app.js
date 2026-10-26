'use strict';

// Bootstrap owns dropdowns and dismissible alerts. This adds mobile navigation
// around the original sidebar without replacing its desktop layout.
const menu = document.querySelector('[data-menu-toggle]');
const side = document.getElementById('sidebarMenu');
const shade = document.querySelector('.sidebar-shade');
function closeMenu() {
    side?.classList.remove('show');
    if (shade) shade.hidden = true;
    menu?.setAttribute('aria-expanded', 'false');
    document.body.style.overflow = '';
    side?.removeAttribute('role');
    side?.removeAttribute('aria-modal');
    side?.removeAttribute('aria-label');
}
menu?.addEventListener('click', () => {
    const open = side.classList.toggle('show');
    shade.hidden = !open;
    menu.setAttribute('aria-expanded', String(open));
    document.body.style.overflow = open ? 'hidden' : '';
    if (open) {
        side.setAttribute('role', 'dialog');
        side.setAttribute('aria-modal', 'true');
        side.setAttribute('aria-label', 'Điều hướng hệ thống');
        side.querySelector('a')?.focus();
    } else closeMenu();
});
shade?.addEventListener('click', () => { closeMenu(); menu?.focus(); });
document.addEventListener('keydown', event => {
    if (!side?.classList.contains('show')) return;
    if (event.key === 'Escape') { closeMenu(); menu?.focus(); }
    if (event.key === 'Tab') {
        const items = [...side.querySelectorAll('a[href],button:not([disabled]),summary')]
            .filter(item => item.getClientRects().length);
        items.push(menu);
        if (event.shiftKey && document.activeElement === items[0]) {
            event.preventDefault(); items.at(-1).focus();
        } else if (!event.shiftKey && document.activeElement === items.at(-1)) {
            event.preventDefault(); items[0].focus();
        }
    }
});
window.matchMedia('(min-width:992px)').addEventListener('change', event => {
    if (event.matches) closeMenu();
});
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
