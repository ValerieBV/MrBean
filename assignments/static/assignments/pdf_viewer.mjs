import {getDocument, GlobalWorkerOptions} from '../core/vendor/pdfjs/pdf.min.mjs';

const assets = new URL('../core/vendor/pdfjs/', import.meta.url);
GlobalWorkerOptions.workerSrc = new URL('pdf.worker.min.mjs', assets).href;

async function openPDF(viewer) {
    const viewport = viewer.querySelector('.pdf-viewport');
    const canvas = viewer.querySelector('canvas');
    const status = viewer.querySelector('[data-pdf-status]');
    const counter = viewer.querySelector('[data-pdf-page]');
    const previous = viewer.querySelector('[data-pdf-prev]');
    const next = viewer.querySelector('[data-pdf-next]');
    const minus = viewer.querySelector('[data-pdf-minus]');
    const plus = viewer.querySelector('[data-pdf-plus]');
    let pdf, pageNumber = 1, zoom = 1, renderTask, generation = 0, lastWidth = 0, resizeFrame = 0;

    async function renderPage() {
        if (!viewport.clientWidth) return;
        const current = ++generation;
        if (renderTask) {
            renderTask.cancel();
            await renderTask.promise.catch(() => {});
        }
        try {
            const page = await pdf.getPage(pageNumber);
            if (current !== generation) return;
            const original = page.getViewport({scale: 1});
            const available = Math.max(1, viewport.clientWidth - 16);
            const scale = available / original.width * zoom;
            const size = page.getViewport({scale});
            const density = Math.min(window.devicePixelRatio || 1, 2);
            canvas.width = Math.ceil(size.width * density);
            canvas.height = Math.ceil(size.height * density);
            canvas.style.width = `${size.width}px`;
            canvas.style.height = `${size.height}px`;
            canvas.hidden = false;
            canvas.setAttribute('aria-label', `Đề bài PDF, trang ${pageNumber} trên ${pdf.numPages}`);
            renderTask = page.render({canvasContext: canvas.getContext('2d'), viewport: size,
                transform: density === 1 ? null : [density, 0, 0, density, 0, 0]});
            await renderTask.promise;
            if (current !== generation) return;
            viewer.dataset.pdfReady = 'true';
            counter.textContent = `Trang ${pageNumber} / ${pdf.numPages}`;
            status.textContent = `Đang xem trang ${pageNumber}. Có thể phóng to để nhìn rõ đề.`;
            previous.disabled = pageNumber <= 1;
            next.disabled = pageNumber >= pdf.numPages;
            minus.disabled = zoom <= 1;
            plus.disabled = zoom >= 2.5;
            const text = await page.getTextContent();
            if (current === generation) viewer.querySelector('[data-pdf-text]').textContent = text.items.map(item => item.str || '').join(' ');
        } catch (error) {
            if (current === generation && error.name !== 'RenderingCancelledException') {
                status.textContent = 'Chưa hiển thị được trang PDF. Dùng liên kết bên dưới để mở đề trong tab mới.';
            }
        }
    }

    try {
        // All document bytes are read through the authenticated, same-site endpoint.
        // No PDF JavaScript or embedded links/forms are executed by this viewer.
        pdf = await getDocument({url: viewer.dataset.pdfUrl, withCredentials: true,
            standardFontDataUrl: new URL('standard_fonts/', assets).href,
            wasmUrl: new URL('wasm/', assets).href,
            isEvalSupported: false, enableXfa: false}).promise;
        previous.addEventListener('click', () => {pageNumber = Math.max(1, pageNumber - 1); renderPage();});
        next.addEventListener('click', () => {pageNumber = Math.min(pdf.numPages, pageNumber + 1); renderPage();});
        minus.addEventListener('click', () => {zoom = Math.max(1, zoom - .25); renderPage();});
        plus.addEventListener('click', () => {zoom = Math.min(2.5, zoom + .25); renderPage();});
        new ResizeObserver(entries => {
            const width = Math.round(entries[0].contentRect.width);
            if (width === lastWidth) return;
            lastWidth = width;
            cancelAnimationFrame(resizeFrame);
            if (width > 0) resizeFrame = requestAnimationFrame(() => renderPage());
        }).observe(viewport);
    } catch {
        status.textContent = 'Không mở được PDF. Thử tải lại trang hoặc mở đề trong tab mới.';
    }
}

const viewers = document.querySelectorAll('[data-pdf-url]');
if ('IntersectionObserver' in window) {
    const visible = new IntersectionObserver(entries => {
        for (const entry of entries) {
            if (entry.isIntersecting) {visible.unobserve(entry.target);openPDF(entry.target);}
        }
    }, {rootMargin:'160px'});
    viewers.forEach(viewer => visible.observe(viewer));
} else {
    viewers.forEach(openPDF);
}
