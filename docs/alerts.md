# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

Rule nằm trong [`../config/alert_rules.yaml`](../config/alert_rules.yaml), ngưỡng khớp với threshold của dashboard ([`../config/dashboard.yaml`](../config/dashboard.yaml)) và SLO/guardrail ([`../config/slo.yaml`](../config/slo.yaml)). Mọi runbook đi theo thứ tự Metrics → Logs → Traces. Lệnh lọc log dùng chung:

```bash
# In các response chậm nhất trong log (correlation_id, latency, feature)
python -c "import json; rs=[json.loads(l) for l in open('data/logs.jsonl', encoding='utf-8')]; [print(r['ts'], r['correlation_id'], r.get('latency_ms'), r.get('feature')) for r in sorted((r for r in rs if r.get('event')=='response_sent'), key=lambda r: r['latency_ms'])[-5:]]"
```

Trên Langfuse (project cá nhân), mở **Tracing → Traces**, lọc metadata `correlation_id = <id>` rồi so sánh thời gian/trạng thái của hai observation con `retrieval` và `llm-generation` dưới root `lab-agent-run`.

## Alert 1

- Tên: `HighLatencyP95`
- Severity: P2
- Duration: 5m
- Kênh thông báo: Slack `#day13-llmops-alerts`
- SLI/SLO liên quan: `fast_successful_requests`: 99.5% request trả lời trong ≤ 3000 ms (28 ngày)
- Điều kiện và thời gian duy trì: P95 `response_sent.latency_ms` trong cửa sổ 5 phút > 3000 ms, kéo dài liên tục 5 phút
- Ảnh hưởng tới người dùng: câu trả lời chậm rõ rệt; mỗi request > 3000 ms tiêu vào error budget của SLO
- Ba bước kiểm tra đầu tiên:
  1. Metrics: panel *Latency percentiles and TTFT*. Nếu P95 tăng nhưng TTFT P95 không đổi thì phần chậm nằm trước LLM (retrieval/prompt fetch). Xác định phút bắt đầu tăng.
  2. Logs: chạy lệnh lọc ở trên, lấy `correlation_id` của request chậm trong khoảng thời gian đó; kiểm tra có tập trung vào một `feature` không.
  3. Traces: mở trace cùng `correlation_id`. Span `retrieval` dài bất thường nghĩa là vector store chậm; khoảng trống giữa `retrieval` và `llm-generation` nghĩa là chậm ở bước fetch prompt; `llm-generation` dài nghĩa là LLM chậm.
- Mitigation tạm thời: nếu do retrieval, tắt/giảm timeout retrieval và trả lời bằng fallback không dùng context; nếu do prompt fetch, kiểm tra Langfuse và dựa vào cache/fallback local; giảm concurrency hoặc scale thêm worker vì handler đang chạy đồng bộ.
- Owner: `llmops-oncall`

## Alert 2

- Tên: `HighErrorRate`
- Severity: P1
- Duration: 5m
- Kênh thông báo: Slack `#day13-llmops-alerts`
- SLI/SLO liên quan: `fast_successful_requests` (request lỗi là bad event); guardrail `error_rate_pct_max: 2` và `retrieval_success_rate_pct_min: 90`
- Điều kiện và thời gian duy trì: `count(request_failed) / count(request_received) * 100` trong cửa sổ 5 phút > 2%, kéo dài liên tục 5 phút
- Ảnh hưởng tới người dùng: người dùng nhận HTTP 500, không có câu trả lời; error budget bị tiêu rất nhanh
- Ba bước kiểm tra đầu tiên:
  1. Metrics: panel *Error rate and retrieval success*: xem breakdown `error_type` và retrieval success có giảm cùng lúc không (`GET /metrics` → `error_breakdown`).
  2. Logs: lọc `event == "request_failed"`, đọc `error_type`, `tool_name`, `tool_success` và `payload.detail`; lấy một `correlation_id`.
  3. Traces: mở trace cùng `correlation_id`, tìm observation có level `ERROR` (ví dụ `retrieval` báo `RuntimeError: Vector store timeout`) và xem lỗi xảy ra trước hay sau `llm-generation`.
- Mitigation tạm thời: nếu lỗi ở retrieval, bật fallback trả lời không dùng context hoặc retry có giới hạn; nếu lỗi bắt đầu sau khi đổi prompt/model, rollback label `production` về version trước; tạm tắt feature bị ảnh hưởng.
- Owner: `llmops-oncall`

## Alert 3

- Tên: `CostBurnRateHigh`
- Severity: P3
- Duration: 15m
- Kênh thông báo: Slack `#day13-llmops-alerts`
- SLI/SLO liên quan: guardrail `daily_cost_usd_max: 2.5` (panel *Cost over time*, threshold total ≤ 2.5 USD)
- Điều kiện và thời gian duy trì: tổng `response_sent.cost_usd` trong 1 giờ gần nhất × 24 > 2.5 USD (tốc độ đốt tiền vượt ngân sách ngày), kéo dài liên tục 15 phút
- Ảnh hưởng tới người dùng: chưa gây lỗi ngay nhưng sẽ vượt ngân sách; câu trả lời thường dài bất thường
- Ba bước kiểm tra đầu tiên:
  1. Metrics: so sánh panel *Cost over time* với *Input and output tokens*. Cost tăng cùng `tokens_out` thì output dài ra; cùng traffic thì do lưu lượng tăng.
  2. Logs: lọc `response_sent` có `tokens_out`/`cost_usd` cao nhất, lấy `correlation_id`, kiểm tra có tập trung vào một `feature`/`model` không.
  3. Traces: mở trace cùng `correlation_id`, xem `llm-generation`: usage, cost, model và prompt name/version. Nếu prompt version vừa đổi thì so với version trước.
- Mitigation tạm thời: rollback label `production` về prompt version trước; giới hạn `max_tokens` output; rate-limit feature/user gây tăng đột biến.
- Owner: `llmops-oncall`
