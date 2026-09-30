# Báo cáo cá nhân — K4-L3A Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:**
- **MSSV:**
- **Lớp:** K4-L3A
- **Repository URL:**
- **Commit SHA cuối:**
- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1`
- **Tên project Langfuse cá nhân:** `day13-k4-l3a-2A2026022741`

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
| Trace list | [`evidence/06-trace-list.png`](evidence/06-trace-list.png), [`evidence/06-trace-list.json`](evidence/06-trace-list.json) |
| Trace waterfall | [`evidence/07-trace-waterfall.json`](evidence/07-trace-waterfall.json) |
| Trace metadata | [`evidence/08-trace-metadata.json`](evidence/08-trace-metadata.json) |
| Prompt versions | [`evidence/09-prompt-versions.json`](evidence/09-prompt-versions.json) |
| Prompt rollback | [`evidence/10-prompt-rollback.json`](evidence/10-prompt-rollback.json) |
| Dashboard runtime | [`evidence/11-dashboard-overview.png`](evidence/11-dashboard-overview.png) |
| Incident metric | [`evidence/12-incident-metric.png`](evidence/12-incident-metric.png), [`evidence/12-incident-metric.txt`](evidence/12-incident-metric.txt) |
| Incident log | [`evidence/13-incident-log.txt`](evidence/13-incident-log.txt) |
| Incident trace | [`evidence/14-incident-trace.json`](evidence/14-incident-trace.json) |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 (21 records: 20 thiếu `correlation_id`, 20 thiếu enrichment, 0 correlation ID) — [00-baseline.txt](evidence/00-baseline.txt) | CP1: 100/100 — [02-log-validator.txt](evidence/02-log-validator.txt) | Đã lưu output baseline, chuyển log cũ ra khỏi repo rồi chạy lại load test trước khi đo |
| `validate_dashboard.py` | HỢP LỆ: 6/6 panel (contract) | CP2: HỢP LỆ 6/6 — [03-dashboard-validator.txt](evidence/03-dashboard-validator.txt) | Dashboard runtime dựng bằng `scripts/build_dashboard.py` từ `data/logs.jsonl` |
| `pytest` | 22 passed | CP2: 33 passed | +11 test cho PII, correlation ID, enrichment, thứ tự processor |
| Số traces hợp lệ | 0 child observation (starter chỉ có root) | CP2: 28 traces có root + `retrieval` + `llm-generation` — [06-trace-list.json](evidence/06-trace-list.json) | Đếm qua Langfuse Observations API v2 |
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
- **Cách promote và rollback `production`:** dùng SDK `update_prompt` (label là duy nhất giữa các version nên gắn `production` cho version nào thì version kia tự mất label). Trước: `production` = v1 → `req-86ae0e98`, trace `a91ff19f4389087cc6cc95d5ff41904a` (v1). Promote: `update_prompt(version=2, new_labels=[candidate, production])` → `req-312d005f`, trace `ce5b4e4ac9984f5abd77d2d6b1a01273` (v2, tokens_in 43). Rollback: `update_prompt(version=1, new_labels=[baseline, production])` → `req-49c1c49e`, trace `05f5da75540f54e345827f672180eb31` (v1, tokens_in 32). App cache prompt 60 s theo kiểu stale-while-revalidate, nên request đầu tiên sau mỗi lần đổi label vẫn nhận version cũ (`req-a61c1a68`, `req-fa05c49e`); rollback có hiệu lực sau tối đa ~60 s + 1 request. Chi tiết: [10-prompt-rollback.json](evidence/10-prompt-rollback.json), [09-prompt-versions.json](evidence/09-prompt-versions.json).

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** [scripts/build_dashboard.py](../scripts/build_dashboard.py) đọc contract [config/dashboard.yaml](../config/dashboard.yaml) (tên panel, đơn vị, threshold, time range 60 phút, refresh 30 s) và tính aggregation từ `data/logs.jsonl`, sinh `data/dashboard.html` (chạy `--watch` để cập nhật mỗi 30 s). Sáu panel: latency P50/P95/P99 + TTFT P95; traffic (count, req/phút); error rate + breakdown `error_type` + retrieval success; cost theo phút + tổng; tokens input/output; quality mean. Mỗi panel có đơn vị, đường threshold và trạng thái đạt/vượt. Kiểm tra runtime: bật practice `rag_slow` làm latency tăng từ ~470–780 ms lên ~2653 ms.
- **SLO và lý do chọn:** [config/slo.yaml](../config/slo.yaml): 99.5% request (28 ngày) trả lời thành công trong ≤ 3000 ms. Baseline: P50 808 ms, 34/36 request ≤ 3000 ms; hai request vượt đều là cold-start fetch prompt. Hạn chế: `latency_ms` đo trong agent nên không tính thời gian xếp hàng (khi practice `rag_slow`, log ~2.6 s nhưng client chờ ~13 s).
- **Cách tính error budget:** budget = (1 − 99.5%) × tổng request = 0.5%. Với giả định 1 request/phút: 40 320 request/28 ngày → được phép 201 request chậm/lỗi, tương đương 3.36 giờ nếu hỏng toàn bộ. Tiêu > 50% budget thì dừng đổi prompt/model để ưu tiên độ tin cậy.
- **Ba alert và runbook tương ứng:** [config/alert_rules.yaml](../config/alert_rules.yaml) + [docs/alerts.md](../docs/alerts.md): `HighLatencyP95` (P2, P95 > 3000 ms trong 5m), `HighErrorRate` (P1, error rate > 2% trong 5m), `CostBurnRateHigh` (P3, cost 1h × 24 > 2.5 USD trong 15m). Cả ba đều symptom-based, gửi Slack `#day13-llmops-alerts`, owner `llmops-oncall`, runbook đi theo Metrics → Logs → Traces.

## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1` (cohort K4, seed 1311, `latency_threshold_ms` 2000, feature bị ảnh hưởng `monitoring`)
- **Khoảng thời gian điều tra:** 2026-09-30 04:36:56Z → 04:37:12Z (11:36:56–11:37:12 giờ VN), chạy `inject_incident.py` + `load_test.py --challenge --concurrency 5`; so với nền 04:34:00–04:36:56Z.
- **Triệu chứng từ metrics:** panel Latency: P95 tăng từ 154 ms lên 2655 ms (~17 lần, vượt ngưỡng 2000 ms của challenge), P50 152 → 2653 ms, trong khi **TTFT P95 giữ nguyên 50 ms**, error rate 0%, retrieval success 100%, token/cost bình thường. Chỉ feature `monitoring` bị ảnh hưởng. TTFT không đổi nên phần chậm nằm trước bước LLM. ([12-incident-metric.png](evidence/12-incident-metric.png), [12-incident-metric.txt](evidence/12-incident-metric.txt))
- **Log line và correlation ID liên quan:** cả 5 `response_sent` trong cửa sổ đều `feature=monitoring`, `latency_ms` 2652–2655, `ttft_ms=50`, `tool_success=true` (chậm nhưng không lỗi). Request chọn để truy vết: `2026-09-30T04:37:00.482909Z req-6ee1d9e6 feature=monitoring latency_ms=2654 ttft_ms=50`. ([13-incident-log.txt](evidence/13-incident-log.txt))
- **Trace ID và span gây ảnh hưởng:** trace `bc7e13903632f02efdf97b7b53595e5b` (metadata `correlation_id=req-6ee1d9e6`): root `lab-agent-run` 2660 ms = **`retrieval` 2506 ms** + `llm-generation` 153 ms, không có khoảng trống giữa hai span. Cả 5 trace challenge đều có `retrieval` ≈ 2500 ms, trong khi 10 trace ngay trước sự cố có `retrieval` ≈ 0 ms. ([14-incident-trace.json](evidence/14-incident-trace.json))
- **Root cause:** bước retrieval (vector store) bị chậm ~2.5 s mỗi request (incident `rag_slow` trong `app/mock_rag.py`), không phải LLM hay prompt. Tác động bị khuếch đại vì `/chat` là `async` nhưng gọi `agent.run` đồng bộ, nên request retrieval chậm chặn event loop: với concurrency 5, các request xếp hàng tuần tự và client chờ tới ~13.3 s, dù `latency_ms` phía server chỉ ~2.65 s.
- **Fix action:** tắt incident (`python scripts/inject_incident.py --disable`), tương đương khôi phục vector store. Kiểm chứng bằng cùng 5 query challenge lúc 04:40:07Z: P95 feature `monitoring` về 152 ms, client ~0.6–0.8 s (`req-0fe3fc4d`, `req-a61d5684`, `req-f74446b0`, `req-59f2086c`, `req-0e9d0ddb`).
- **Preventive measure:** (1) timeout cho retrieval (ví dụ 500 ms) và fallback trả lời không có context, để một vector store chậm không làm hỏng SLO; (2) chạy `agent.run` qua threadpool (`run_in_threadpool`) hoặc chuyển sang I/O async để request chậm không chặn các request khác; (3) thêm SLI latency đo ở biên (`x-response-time-ms`) vì `latency_ms` hiện không thấy thời gian xếp hàng; (4) alert riêng cho latency của span `retrieval` và hạ ngưỡng `HighLatencyP95` về 2000 ms cho feature `monitoring`, vì sự cố này (P95 2655 ms) chưa chạm ngưỡng 3000 ms nên alert hiện tại không kêu.

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
