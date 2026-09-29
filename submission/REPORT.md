# Báo cáo cá nhân — K4-L3A Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:**
- **MSSV:**
- **Lớp:** K4-L3A
- **Repository URL:**
- **Commit SHA cuối:**
- **Challenge ID:**
- **Tên project Langfuse cá nhân:** `day13-k4-l3a-<MSSV>`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn |
|---|---|
| Baseline (CP0) | `evidence/00-baseline.txt` |
| Pytest cuối | `evidence/01-pytest.png` |
| Log validator | `evidence/02-log-validator.txt` |
| Dashboard validator | `evidence/03-dashboard-validator.txt` |
| Structured log | `evidence/04-structured-log.txt` |
| PII redaction | `evidence/05-pii-redaction.txt` |
| Trace list | `evidence/06-trace-list.png` |
| Trace waterfall | `evidence/07-trace-waterfall.png` |
| Trace metadata | `evidence/08-trace-metadata.png` |
| Prompt versions | `evidence/09-prompt-versions.png` |
| Prompt rollback | `evidence/10-prompt-rollback.png` |
| Dashboard runtime | `evidence/11-dashboard-overview.png` |
| Incident metric | `evidence/12-incident-metric.png` |
| Incident log | `evidence/13-incident-log.png` |
| Incident trace | `evidence/14-incident-trace.png` |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 (21 records: 20 thiếu `correlation_id`, 20 thiếu enrichment, 0 correlation ID) — [00-baseline.txt](evidence/00-baseline.txt) | CP1: 100/100 — [02-log-validator.txt](evidence/02-log-validator.txt) | Đã lưu output baseline, chuyển log cũ ra khỏi repo rồi chạy lại load test trước khi đo |
| `validate_dashboard.py` | HỢP LỆ: 6/6 panel (contract) | CP2: HỢP LỆ 6/6 — [03-dashboard-validator.txt](evidence/03-dashboard-validator.txt) | Dashboard runtime dựng bằng `scripts/build_dashboard.py` từ `data/logs.jsonl` |
| `pytest` | 22 passed | CP1: 34 passed | +12 test cho PII, correlation ID, enrichment, thứ tự processor |
| Số traces hợp lệ | 0 child observation (starter chỉ có root) | CP2: 23 traces có root + `retrieval` + `llm-generation` | Đếm qua Langfuse Observations API v2 |
| Số PII leak | 0 (validator) | CP1: 0 — [05-pii-redaction.txt](evidence/05-pii-redaction.txt) | Baseline 0 vì `summarize_text` đã scrub `message_preview`, nhưng processor chưa đăng ký nên field khác (error detail, event) vẫn có thể lộ |
| Latency P95 / TTFT P95 | | CP2: 3997 ms / 50 ms (36 request, cửa sổ 60 phút) | P95 bị kéo lên bởi 2 request cold-start fetch prompt; khi chạy `rag_slow` latency ~2653 ms |
| Retrieval success rate | | CP2: 100% (0 `request_failed`) | Chưa chạy practice `tool_fail` |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** `CorrelationIdMiddleware` ([app/middleware.py](../app/middleware.py)) gọi `clear_contextvars()` đầu mỗi request để không rò context từ request trước. Nếu client gửi `x-request-id` đúng format `req-<8-hex>` thì dùng lại, ngược lại (thiếu, sai format, chuỗi độc hại) sinh mới `req-{uuid4().hex[:8]}`. ID được `bind_contextvars(correlation_id=...)`, lưu vào `request.state` (để truyền sang `LabAgent.run` và trace metadata), rồi trả lại qua header `x-request-id` cùng `x-response-time-ms` và field `correlation_id` trong response body.
- **Các metadata được ghi vào structured log:** mọi dòng có `ts` (ISO UTC), `level`, `service`, `event`, `correlation_id`. Trong `/chat` ([app/main.py](../app/main.py)) bind trước `request_received`: `user_id_hash` (SHA-256 12 ký tự, không log `user_id` thô), `session_id`, `feature`, `model`, `env`. `response_sent` bổ sung `latency_ms`, `ttft_ms`, `tokens_in`, `tokens_out`, `cost_usd`, `quality_score`, `tool_name`, `tool_success`. Ví dụ: [04-structured-log.txt](evidence/04-structured-log.txt).
- **Cách bảo đảm PII được scrub trước khi ghi:** `scrub_event` được đăng ký trong chuỗi processor của structlog ([app/logging_config.py](../app/logging_config.py)) sau `format_exc_info` (traceback cũng được scrub) và **trước** `JsonlFileProcessor` và `JSONRenderer`, nên dữ liệu thô không bao giờ được serialize/ghi file. Processor scrub đệ quy mọi giá trị chuỗi (kể cả dict/list lồng nhau), trừ các field do app tự sinh (`ts`, `level`, `correlation_id`, `Pattern trong [app/pii.py](../app/pii.py) (giữ nguyên rule của đề): email, điện thoại VN (`+84`/`0` + 9 số, cho phép dấu cách/chấm/gạch), CCCD (12 số), thẻ thanh toán (16 số, nhóm 4-4-4-4). Nhãn thay thế là `[REDACTED_<LOẠI>]`.phần dãy số dài.
- **Cách kiểm chứng kết quả:** (1) `python scripts/validate_logs.py` đạt 100/100 trên log mới (12 correlation ID, 0 thiếu field, 0 PII leak). (2) Gửi request chứa PII giả đủ 4 loại → log chỉ còn `[REDACTED_*]` ([05-pii-redaction.txt](evidence/05-pii-redaction.txt)). (3) Gửi `x-request-id: req-1a2b3c4d` → response trả đúng ID đó. (4) Tests: [tests/test_pii.py](../tests/test_pii.py) và [tests/test_correlation_logging.py](../tests/test_correlation_logging.py) kiểm tra sinh/nhận/thay ID sai format, enrichment đúng từng request (không rò context giữa 2 request liên tiếp), PII không xuất hiện trong file log, và `scrub_event` đứng trước file writer/renderer.

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** key trong `.env` thuộc project Langfuse cá nhân; mọi trace được tạo bằng workload tự chạy (`scripts/load_test.py`, `--concurrency 5`, practice `rag_slow`). Mỗi trace có `correlation_id` trùng với một dòng trong `data/logs.jsonl` của tôi.
- **Cấu trúc root/retrieval/generation observations:** root `lab-agent-run` (type `agent`, starter) có hai con: `retrieval` (type `retriever`, `@observe` trên `retrieve()` trong [app/mock_rag.py](../app/mock_rag.py)) và `llm-generation` (type `generation`, `@observe` trên `FakeLLM.generate()` trong [app/mock_llm.py](../app/mock_llm.py)). Generation ghi `model`, `usage_details` (input/output tokens), `cost_details` (input/output USD, cùng bảng giá `PRICE_PER_MTOK_USD` với `cost_usd` trong log) và `completion_start_time` (TTFT). Prompt được gắn vào generation qua `propagate_attributes(prompt=...)` có sẵn trong agent. Cả hai observation con đều `capture_input=False, capture_output=False` vì prompt đã compile chứa message thô có thể có PII.
- **Cách nối trace với log:** `correlation_id` từ middleware được truyền vào `LabAgent.run` và đưa vào trace metadata qua `propagate_attributes(metadata=...)`, nên cả root và observation con đều có `correlation_id`. Từ một dòng log, lọc trace trên Langfuse theo metadata `correlation_id` (ví dụ `req-56cb3a22` → trace `9ef9a0a0a709c5c1c9fc71b571ef555f`).
- **Prompt name:** `day13-chat` (text prompt, giữ 3 biến `{{feature}}`, `{{docs}}`, `{{message}}`)
- **Version/label baseline:** version 1 = template gốc, labels `baseline` + `production`
- **Version/label candidate:** version 2 = thêm dòng `Answer in at most 3 short bullet points.`, label `candidate`
- **Trace ID của mỗi version:** cùng input *"Explain why metrics traces and logs work together"*: `baseline` → v1: `req-56cb3a22`, trace `9ef9a0a0a709c5c1c9fc71b571ef555f` (tokens_in 32); `candidate` → v2: `req-cdda450a`, trace `e23e86c516c9bef17237f4a0afdadf33` (tokens_in 43). Metadata root ghi `prompt_source=langfuse`, `prompt_label` và `prompt_version` tương ứng; generation liên kết `day13-chat` v1/v2.
- **Cách promote và rollback `production`:** _(chưa làm — thực hiện trên Langfuse UI và chụp ảnh trước/sau)_

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** [scripts/build_dashboard.py](../scripts/build_dashboard.py) đọc contract [config/dashboard.yaml](../config/dashboard.yaml) (tên panel, đơn vị, threshold, time range 60 phút, refresh 30 s) và tính aggregation từ `data/logs.jsonl`, sinh `data/dashboard.html` (chạy `--watch` để cập nhật mỗi 30 s). Sáu panel: latency P50/P95/P99 + TTFT P95; traffic (count, req/phút); error rate + breakdown `error_type` + retrieval success; cost theo phút + tổng; tokens input/output; quality mean. Mỗi panel có đơn vị, đường threshold và trạng thái đạt/vượt. Kiểm tra runtime: bật practice `rag_slow` làm latency tăng từ ~470–780 ms lên ~2653 ms.
- **SLO và lý do chọn:** [config/slo.yaml](../config/slo.yaml): 99.5% request (28 ngày) trả lời thành công trong ≤ 3000 ms. Baseline: P50 808 ms, 34/36 request ≤ 3000 ms; hai request vượt đều là cold-start fetch prompt. Hạn chế: `latency_ms` đo trong agent nên không tính thời gian xếp hàng (khi practice `rag_slow`, log ~2.6 s nhưng client chờ ~13 s).
- **Cách tính error budget:** budget = (1 − 99.5%) × tổng request = 0.5%. Với giả định 1 request/phút: 40 320 request/28 ngày → được phép 201 request chậm/lỗi, tương đương 3.36 giờ nếu hỏng toàn bộ. Tiêu > 50% budget thì dừng đổi prompt/model để ưu tiên độ tin cậy.
- **Ba alert và runbook tương ứng:** [config/alert_rules.yaml](../config/alert_rules.yaml) + [docs/alerts.md](../docs/alerts.md): `HighLatencyP95` (P2, P95 > 3000 ms trong 5m), `HighErrorRate` (P1, error rate > 2% trong 5m), `CostBurnRateHigh` (P3, cost 1h × 24 > 2.5 USD trong 15m). Cả ba đều symptom-based, gửi Slack `#day13-llmops-alerts`, owner `llmops-oncall`, runbook đi theo Metrics → Logs → Traces.

## 7. Điều tra challenge

- **Challenge ID:**
- **Khoảng thời gian điều tra:**
- **Triệu chứng từ metrics:**
- **Log line và correlation ID liên quan:**
- **Trace ID và span gây ảnh hưởng:**
- **Root cause:**
- **Fix action:**
- **Preventive measure:**

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:**
- **Một lỗi/blocker đã gặp:**
- **Cách tìm nguyên nhân và xử lý:**
- **Cách hiểu luồng Metrics → Logs → Traces:**
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:**
- **Điều quan trọng nhất đã học:**
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:**

## 9. Checklist trước khi nộp

- [ ] Kết quả và evidence thuộc commit SHA cuối.
- [ ] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [ ] Incident evidence nối đúng metric → log → trace.
- [ ] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [ ] Repository chạy lại được theo README.
- [ ] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
