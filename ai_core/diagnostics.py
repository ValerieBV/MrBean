"""Safe grading diagnostics; never persist provider messages or credentials."""
import json
import openai


FALLBACK_HINTS = {
    'provider_not_configured': 'Tiến trình chấm chưa nhận được API key. Quản trị viên cần kiểm tra .env và khởi động lại tiến trình chấm.',
    'ai_authentication': 'OpenAI từ chối API key của tiến trình chấm. Kiểm tra key và khởi động lại tiến trình sau khi đổi cấu hình.',
    'ai_permission_denied': 'Dự án OpenAI chưa được cấp quyền sử dụng chức năng hoặc model cần cho bài này.',
    'ai_quota_exceeded': 'Tài khoản API chưa đủ hạn mức sử dụng. Kiểm tra Billing và Usage trên OpenAI Platform.',
    'ai_rate_limited': 'OpenAI đang giới hạn tốc độ yêu cầu. Có thể thử một lần nộp mới sau khi hạn mức phục hồi.',
    'ai_model_unavailable': 'Model chấm hoặc chuyển ghi âm chưa có trong dự án OpenAI. Kiểm tra cấu hình và quyền truy cập model.',
    'ai_request_invalid': 'OpenAI không chấp nhận yêu cầu chấm. Quản trị viên cần kiểm tra cấu hình model, thư viện và định dạng bài làm.',
    'ai_connection_error': 'Tiến trình chấm không kết nối được OpenAI. Kiểm tra Internet hoặc proxy trên máy chạy tiến trình.',
    'ai_provider_unavailable': 'Dịch vụ OpenAI chưa xử lý được yêu cầu. Bài đã được giữ lại để giáo viên chấm.',
    'ai_timeout': 'Yêu cầu AI vượt thời gian chờ. Bài đã chuyển sang giáo viên để không tiếp tục chờ.',
    'ai_deadline_exceeded': 'Bài chưa hoàn tất đánh giá AI trong 5 phút từ lúc nộp. Kiểm tra tiến trình chấm có chạy cùng database với website hay không.',
    'ai_uncertain_evidence': 'AI chưa đọc được bài làm một cách chắc chắn. Giáo viên cần xem ảnh hoặc nghe bản ghi để chấm.',
    'ai_invalid_evidence': 'Ảnh hoặc bản ghi chưa đủ điều kiện để AI đánh giá. Giáo viên cần kiểm tra bài làm gốc.',
    'ai_evidence_missing': 'Tiến trình chấm không tìm thấy tệp bài làm. Kiểm tra thư mục media và cấu hình lưu trữ dùng chung.',
    'ai_invalid_reference': 'Bài đã giao thiếu hoặc có mẫu chấm không hợp lệ. Giáo viên cần kiểm tra yêu cầu và mẫu của bài.',
    'ai_invalid_result': 'Phản hồi AI không đủ dữ liệu hợp lệ để tính điểm. Giáo viên cần kiểm tra và chấm bài.',
    'ai_error': 'Lượt đánh giá AI chưa thành công. Bản ghi cũ có thể chưa lưu nguyên nhân chi tiết; quản trị viên cần kiểm tra tiến trình chấm.',
}


def diagnostic_code(reason):
    return reason if isinstance(reason, str) and reason in FALLBACK_HINTS else 'ai_error'


def failure_reason(error):
    """Classify known failures without storing str(error), bodies, or API keys."""
    if isinstance(error, (TimeoutError, openai.APITimeoutError)):
        return 'ai_timeout'
    if isinstance(error, openai.AuthenticationError):
        return 'ai_authentication'
    if isinstance(error, openai.PermissionDeniedError):
        return 'ai_permission_denied'
    if isinstance(error, openai.RateLimitError):
        return 'ai_quota_exceeded' if error.code == 'insufficient_quota' else 'ai_rate_limited'
    if isinstance(error, openai.NotFoundError):
        return 'ai_model_unavailable'
    if isinstance(error, openai.BadRequestError):
        return 'ai_request_invalid'
    if isinstance(error, openai.APIConnectionError):
        return 'ai_connection_error'
    if isinstance(error, openai.APIStatusError):
        return 'ai_provider_unavailable'
    if isinstance(error, FileNotFoundError):
        return 'ai_evidence_missing'
    if isinstance(error, json.JSONDecodeError):
        return 'ai_invalid_result'
    if isinstance(error, ValueError):
        reason = error.args[0] if error.args else None
        if not isinstance(reason, str):
            return 'ai_error'
        if reason == 'provider_not_configured':
            return reason
        if reason == 'needs_manual':
            return 'ai_uncertain_evidence'
        if reason in ('missing_rubric', 'invalid_rubric', 'reading_reference_required', 'recording_and_reading_reference_required'):
            return 'ai_invalid_reference'
        if reason in ('invalid_audio_size', 'invalid_image_size', 'invalid_transcript'):
            return 'ai_invalid_evidence'
        if reason in ('invalid_result', 'invalid_feedback', 'invalid_counts', 'invalid_word', 'invalid_count'):
            return 'ai_invalid_result'
    return 'ai_error'


def review_status_label(job):
    if job.status == 'graded' and job.completion_status == 'pending':
        return 'Cần xác nhận mức hoàn thành'
    return 'Chờ giáo viên xác nhận' if job.status == 'ai_reviewed' else 'Cần chấm thủ công'


def staff_grading_state(job):
    if job.kind not in ('speaking', 'vocabulary') or job.status == 'graded':
        return None
    states = {
        'queued': ('Đang chờ AI xử lý', 'Bài đã được tiếp nhận, đang chờ tiến trình AI đánh giá và chưa chuyển sang chấm thủ công.'),
        'processing': ('AI đang xử lý bài', 'Hệ thống đang đánh giá bài làm trước khi chuyển kết quả gợi ý cho giáo viên xác nhận.'),
        'ai_reviewed': ('AI đã đánh giá — chờ giáo viên xác nhận', 'AI đã tạo điểm và nhận xét gợi ý. Giáo viên kiểm tra bài làm, điều chỉnh nếu cần và xác nhận điểm cuối cùng ở biểu mẫu bên dưới.'),
        'manual': ('Bài cần chấm thủ công', 'Lượt đánh giá AI chưa hoàn tất. Giáo viên có thể chấm từ bài làm gốc.'),
    }
    if job.status not in states:
        return None
    title, message = states[job.status]
    reason = diagnostic_code(job.fallback_reason) if job.status == 'manual' else ''
    return {'status': job.status, 'title': title, 'message': message,
            'reason': reason, 'hint': FALLBACK_HINTS.get(reason, '')}
