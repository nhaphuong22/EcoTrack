import os
import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

class ExperimentLogger:
    """
    Automated Experiment Logger for LLM Agent & ML reasoning calls.
    Captures prompt, tools used, latencies, tokens, and model outputs
    to serve as empirical benchmark data for scientific papers.
    """
    def __init__(self, log_dir: str = "experiments/logs", log_filename: str = "agent_eval_logs.jsonl"):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.log_dir = os.path.join(self.base_dir, "..", log_dir)
        self.log_path = os.path.join(self.log_dir, log_filename)
        os.makedirs(self.log_dir, exist_ok=True)

    def log_interaction(
        self,
        user_message: str,
        response_text: str,
        tools_called: List[str],
        latency_ms: float,
        model_name: str,
        tools_data: Optional[Dict[str, Any]] = None,
        case_study_id: Optional[str] = None,
        is_success: bool = True,
        error_msg: Optional[str] = None
    ) -> Dict[str, Any]:
        """Ghi lại 1 lượt tương tác (inference turn) vào log thực nghiệm."""
        timestamp_iso = datetime.now(timezone.utc).isoformat()
        
        # Heuristic intent classification
        msg_lower = user_message.lower()
        if any(w in msg_lower for w in ["bất thường", "sự cố", "anomaly", "chẩn đoán", "nguyên nhân", "lỗi"]):
            intent = "fault_diagnostics"
        elif any(w in msg_lower for w in ["dự báo", "forecast", "ngày mai", "đỉnh", "peak"]):
            intent = "load_forecasting"
        elif any(w in msg_lower for w in ["tổng quan", "tiêu thụ", "kwh", "chỉ số", "metrics"]):
            intent = "metrics_overview"
        elif any(w in msg_lower for w in ["chi phí", "tiền", "lãng phí", "cost"]):
            intent = "cost_estimation"
        else:
            intent = "general_query"

        # Rough token approximation (1 word ~ 1.3 tokens)
        prompt_tokens = int(len(user_message.split()) * 1.3) + 150 # 150 for system prompt
        completion_tokens = int(len(response_text.split()) * 1.3)
        total_tokens = prompt_tokens + completion_tokens

        # Groundedness indicator: check if response quotes actual numbers from tools
        is_grounded = bool(tools_called and len(tools_called) > 0 and any(char.isdigit() for char in response_text))

        record = {
            "log_id": f"EXP-{int(time.time() * 1000)}",
            "timestamp": timestamp_iso,
            "case_study_id": case_study_id,
            "intent": intent,
            "user_query": user_message,
            "model_name": model_name,
            "tools_called": tools_called,
            "latency_ms": round(latency_ms, 2),
            "estimated_tokens": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens
            },
            "is_grounded": is_grounded,
            "is_success": is_success,
            "error_msg": error_msg,
            "response_snippet": response_text[:200] + ("..." if len(response_text) > 200 else ""),
            "full_response": response_text
        }

        # Append to jsonl
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[ExperimentLogger] Error writing log: {e}")

        return record

    def get_summary_statistics(self) -> Dict[str, Any]:
        """Tính toán các chỉ số thống kê từ tập log để đưa vào bài báo."""
        if not os.path.exists(self.log_path):
            return {
                "total_queries": 0,
                "average_latency_ms": 0.0,
                "tool_usage_counts": {},
                "intents_distribution": {},
                "grounded_ratio": 0.0
            }

        total = 0
        latencies = []
        tool_counts: Dict[str, int] = {}
        intent_counts: Dict[str, int] = {}
        grounded_count = 0

        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    total += 1
                    latencies.append(item.get("latency_ms", 0.0))
                    
                    intent = item.get("intent", "other")
                    intent_counts[intent] = intent_counts.get(intent, 0) + 1
                    
                    for t in item.get("tools_called", []):
                        tool_counts[t] = tool_counts.get(t, 0) + 1
                        
                    if item.get("is_grounded", False):
                        grounded_count += 1
                except Exception:
                    continue

        avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0.0
        grounded_ratio = round(grounded_count / total, 4) if total > 0 else 0.0

        return {
            "total_queries": total,
            "average_latency_ms": avg_latency,
            "tool_usage_counts": tool_counts,
            "intents_distribution": intent_counts,
            "grounded_ratio": grounded_ratio
        }

# Global Singleton Instance
experiment_logger = ExperimentLogger()
