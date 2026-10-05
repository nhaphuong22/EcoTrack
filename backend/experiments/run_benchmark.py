import os
import sys
import json
import time

# Ensure backend root is in sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass


from src.agent.orchestrator import copilot_orchestrator
from src.agent.experiment_logger import experiment_logger

def run_case_study_benchmark():
    benchmark_file = os.path.join(os.path.dirname(__file__), "benchmark", "case_studies.json")
    if not os.path.exists(benchmark_file):
        print(f"Error: {benchmark_file} not found!")
        return

    with open(benchmark_file, "r", encoding="utf-8") as f:
        cases = json.load(f)

    print("=" * 80)
    print("🚀 ECOTRACK EXPERIMENTAL BENCHMARK: LLM AGENT FDD EVALUATION")
    print(f"Dataset: BDG2 / ASHRAE Benchmark | Total Test Cases: {len(cases)}")
    print("=" * 80)

    total_prompts = 0
    correct_tools_calls = 0
    keyword_hit_rates = []
    latencies = []

    for case in cases:
        case_id = case["id"]
        name = case["name"]
        expected_tools = set(case.get("expected_tools", []))
        keywords = [kw.lower() for kw in case.get("ground_truth_keywords", [])]

        severity = case.get("telemetry_data", {}).get("severity", "UNKNOWN")
        print(f"\n📌 Running [{case_id}] {name} ({severity})")
        print(f"   Context: {case['operational_context']['building_status']} | Outdoor Temp: {case['operational_context']['outdoor_temperature_c']}°C")

        for prompt in case["test_prompts"]:
            total_prompts += 1
            t_start = time.time()
            reply, tools_used = copilot_orchestrator.process_chat(prompt)
            duration_ms = (time.time() - t_start) * 1000
            latencies.append(duration_ms)

            # Evaluate tool calling
            tools_set = set(tools_used)
            tool_match = bool(expected_tools.intersection(tools_set))
            if tool_match:
                correct_tools_calls += 1

            # Evaluate keyword grounding
            reply_lower = reply.lower()
            hits = sum(1 for kw in keywords if kw in reply_lower)
            hit_ratio = hits / len(keywords) if keywords else 1.0
            keyword_hit_rates.append(hit_ratio)

            print(f"   - Query: '{prompt}'")
            print(f"     ➔ Tools: {tools_used} (Expected: {list(expected_tools)}) | Match: {'✅' if tool_match else '⚠️'}")
            print(f"     ➔ RCA Keyword Grounding: {hits}/{len(keywords)} ({hit_ratio:.0%}) | Latency: {duration_ms:.1f}ms")

    # Final Academic Summary Report
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    tool_accuracy = (correct_tools_calls / total_prompts * 100) if total_prompts else 0.0
    avg_keyword_hit = (sum(keyword_hit_rates) / len(keyword_hit_rates) * 100) if keyword_hit_rates else 0.0

    print("\n" + "=" * 80)
    print("📊 BẢNG TỔNG HỢP CHỈ SỐ THỰC NGHIỆM ĐƯA VÀO BÀI BÁO (BENCHMARK SUMMARY)")
    print("=" * 80)
    print(f"• Tổng số lượt truy vấn thử nghiệm (N):       {total_prompts}")
    print(f"• Độ chính xác lựa chọn Tool (Tool Accuracy):  {tool_accuracy:.1f}%")
    print(f"• Độ bám sát tri thức RCA (Domain Grounding): {avg_keyword_hit:.1f}%")
    print(f"• Thời gian phản hồi trung bình (Avg Latency): {avg_latency:.1f} ms")
    print("=" * 80)
    print("Log chi tiết từng lượt đã được tự động lưu vào: backend/experiments/logs/agent_eval_logs.jsonl\n")

if __name__ == "__main__":
    run_case_study_benchmark()
