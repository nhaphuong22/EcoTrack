import os
import json
import time
from typing import Dict, Any, List, Tuple
from src.agent.prompts import SYSTEM_PROMPT
from src.agent.tools.energy_tools import (
    query_metrics,
    get_anomalies,
    query_forecast_summary,
    calculate_waste_cost
)
from src.agent.experiment_logger import experiment_logger

class CopilotOrchestrator:
    def __init__(self):
        self.gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.openai_key = os.getenv("OPENAI_API_KEY", "").strip()

    def process_chat(
        self,
        user_message: str,
        history: List[Dict[str, Any]] = None,
        anomaly_id: str = None,
    ) -> Tuple[str, List[str]]:
        """
        Processes a chat turn using Cloud LLM or rule-based tool dispatch fallback.
        Returns: (assistant_response_markdown, list_of_tools_called)
        """
        start_time = time.time()
        tools_called = []
        msg_lower = user_message.lower()
        model_name = "heuristic_engine"
        reply = ""

        # Step 1: Tool dispatch decision
        metrics_data = None
        anomalies_data = None
        forecast_data = None

        if any(w in msg_lower for w in ["tổng quan", "tiêu thụ", "kwh", "chỉ số", "metrics", "bao nhiêu điện"]):
            metrics_data = query_metrics()
            tools_called.append("query_metrics")

        if any(w in msg_lower for w in ["bất thường", "sự cố", "anomaly", "anomalies", "lỗi", "chẩn đoán", "nguyên nhân"]):
            anomalies_data = get_anomalies(limit=3)
            tools_called.append("get_anomalies")

        if any(w in msg_lower for w in ["dự báo", "forecast", "ngày mai", "đỉnh", "peak", "24h"]):
            forecast_data = query_forecast_summary()
            tools_called.append("query_forecast_summary")

        if any(w in msg_lower for w in ["chi phí", "tiền", "lãng phí", "cost", "vnd"]):
            tools_called.append("calculate_waste_cost")

        # When the UI sends an anomaly_id, ground the response in that exact
        # event instead of allowing the heuristic fallback to choose another
        # recent anomaly.
        selected_anomaly = None
        if anomaly_id:
            anomaly_candidates = get_anomalies(limit=100)
            selected_anomaly = next(
                (item for item in anomaly_candidates if item.get("id") == anomaly_id),
                None,
            )
            if selected_anomaly:
                anomalies_data = [selected_anomaly]
                if "get_anomalies" not in tools_called:
                    tools_called.append("get_anomalies")

        anomaly_context = ""
        if selected_anomaly:
            anomaly_context = f"""
[ANOMALY CONTEXT - use this exact event]
Anomaly ID: {selected_anomaly['id']}
Timestamp: {selected_anomaly['timestamp']}
Severity: {selected_anomaly['severity']}
Actual consumption: {selected_anomaly['actual_kwh']} kWh
Predicted baseline: {selected_anomaly['predicted_kwh']} kWh
Delta: {selected_anomaly['delta_kwh']} kWh
Anomaly score: {selected_anomaly['anomaly_score']}
Possible reason: {selected_anomaly['reason']}
"""

        # Step 2: Try Cloud API if keys are provided
        if self.gemini_key:
            try:
                from google import genai
                client = genai.Client(api_key=self.gemini_key)
                
                # Context injection from tool executions
                context_str = ""
                if metrics_data:
                    context_str += f"\n[Dữ liệu Tool query_metrics]: {json.dumps(metrics_data, ensure_ascii=False)}"
                if anomalies_data:
                    context_str += f"\n[Dữ liệu Tool get_anomalies]: {json.dumps(anomalies_data, ensure_ascii=False)}"
                if forecast_data:
                    context_str += f"\n[Dữ liệu Tool query_forecast_summary]: {json.dumps(forecast_data, ensure_ascii=False)}"
                context_str += anomaly_context
                
                prompt = f"{SYSTEM_PROMPT}\n{context_str}\n\nNgười dùng: {user_message}"
                response = client.models.generate_content(
                    model="gemini-1.5-flash",
                    contents=prompt
                )
                if response and response.text:
                    reply = response.text
                    model_name = "gemini-1.5-flash"
                    tools_called = tools_called or ["domain_knowledge"]
            except Exception as e:
                # Log error and fallback to structured reasoning
                pass

        if not reply and self.openai_key:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=self.openai_key)
                context_str = ""
                if metrics_data:
                    context_str += f"\n[Dữ liệu Tool query_metrics]: {json.dumps(metrics_data, ensure_ascii=False)}"
                if anomalies_data:
                    context_str += f"\n[Dữ liệu Tool get_anomalies]: {json.dumps(anomalies_data, ensure_ascii=False)}"
                if forecast_data:
                    context_str += f"\n[Dữ liệu Tool query_forecast_summary]: {json.dumps(forecast_data, ensure_ascii=False)}"
                context_str += anomaly_context

                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"{context_str}\n\nCâu hỏi: {user_message}"}
                    ]
                )
                if response.choices:
                    reply = response.choices[0].message.content
                    model_name = "gpt-4o-mini"
                    tools_called = tools_called or ["domain_knowledge"]
            except Exception:
                pass

        # Step 3: Heuristic domain reasoning fallback (guarantees system runs smoothly out of the box)
        if not reply:
            reply, tools_called = self._generate_heuristic_response(user_message, metrics_data, anomalies_data, forecast_data, tools_called)
            model_name = "heuristic_engine"

        # Log turn for academic evaluation
        latency_ms = (time.time() - start_time) * 1000
        experiment_logger.log_interaction(
            user_message=user_message,
            response_text=reply,
            tools_called=tools_called,
            latency_ms=latency_ms,
            model_name=model_name
        )

        return reply, tools_called

    def _generate_heuristic_response(self, query: str, metrics, anomalies, forecast, tools_called) -> Tuple[str, List[str]]:
        msg = query.lower()
        
        if "bất thường" in msg or "sự cố" in msg or "chẩn đoán" in msg or "anom" in msg:
            if not anomalies:
                anomalies = get_anomalies(limit=3)
                if "get_anomalies" not in tools_called:
                    tools_called.append("get_anomalies")
            
            top_anom = anomalies[-1] if anomalies else None
            if top_anom:
                reply = f"""### 🔍 Chẩn đoán sự cố bất thường ({top_anom['id']})

- 📌 **Thời điểm ghi nhận**: `{top_anom['timestamp']}`
- ⚡ **Tiêu thụ thực tế**: **{top_anom['actual_kwh']} kWh** (Baseline dự báo: {top_anom['predicted_kwh']} kWh, chênh lệch **+{top_anom['delta_kwh']} kWh**)
- 🌡️ **Nhiệt độ ngoài trời**: {top_anom['outdoor_temp_c']}°C | **Mức độ**: `{top_anom['severity']}` (Điểm Anomaly: {top_anom['anomaly_score']})

#### 🔎 Phân tích nguyên nhân gốc rễ (RCA)
1. **Lệch pha chu kỳ**: Sự cố xảy ra ngoài giờ vận hành chính (Building unoccupied), nhưng phụ tải chiller và quạt thông gió vẫn duy trì ở công suất tương đương giờ cao điểm.
2. **Nguyên nhân tiềm ẩn**: {top_anom['reason']}.
3. **Tổn thất chi phí**: Ước tính gây lãng phí khoảng **{top_anom['delta_kwh'] * 3100:,.0f} VNĐ** (~${top_anom['delta_kwh'] * 0.125:.2f} USD) cho mỗi giờ duy trì sự cố.

#### 💡 Khuyến nghị cho Kỹ sư vận hành
- [ ] Kiểm tra actuator và van damper gió tươi tại buồng AHU tầng kỹ thuật.
- [ ] Xác minh trạng thái override thủ công trên giao diện BMS trung tâm.
- [ ] Đặt lại lịch hẹn giờ tắt chiller trước 19:00 đối với các khu vực văn phòng cho thuê."""
                return reply, tools_called

        if "dự báo" in msg or "forecast" in msg or "ngày mai" in msg or "đỉnh" in msg:
            if not forecast:
                forecast = query_forecast_summary()
                if "query_forecast_summary" not in tools_called:
                    tools_called.append("query_forecast_summary")
            reply = f"""### 📈 Báo cáo dự báo phụ tải điện 24h tới (XGBoost Engine)

- ⚡ **Công suất đỉnh dự kiến**: **{forecast['expected_peak_kw']} kW** tại thời điểm `{forecast['peak_timestamp']}`.
- 📊 **Tiêu thụ trung bình**: **{forecast['average_forecast_kwh']} kWh/giờ**.
- 🎯 **Dải tin cậy 95%**: `{forecast['confidence_interval_95']}` (theo mô hình chuỗi thời gian).

#### 💡 Khuyến nghị tối ưu biểu giá điện (Peak Shaving)
- Thực hiện **Pre-cooling (làm mát sớm)** trước khung giờ 13:00 - 15:30 khoảng 1.5 giờ khi biểu giá điện còn ở mức bình thường để giảm 15-20% công suất đỉnh giờ cao điểm."""
            return reply, tools_called

        # Default overview summary
        if not metrics:
            metrics = query_metrics()
            if "query_metrics" not in tools_called:
                tools_called.append("query_metrics")
                
        reply = f"""### 🏢 Báo cáo tổng quan năng lượng EcoTrack ({metrics['building_id']})

- ⚡ **Tổng điện năng tiêu thụ (30 ngày)**: **{metrics['total_consumption_kwh']:,.1f} kWh** (Đường cơ sở: {metrics['baseline_kwh']:,.1f} kWh)
- 🚀 **Công suất đỉnh (Peak Demand)**: **{metrics['peak_demand_kw']} kW**
- ⚠️ **Số điểm bất thường phát hiện**: **{metrics['anomalies_detected']} điểm** (Isolation Forest)
- 💸 **Ước tính lãng phí tích lũy**: **{metrics['estimated_waste_vnd']:,.0f} VNĐ** (~${metrics['estimated_waste_usd']:,.2f} USD)

Tôi có thể giúp anh/chị:
1. Phân tích chi tiết từng sự cố bất thường gần nhất.
2. Đánh giá biểu đồ phụ tải dự báo trong 24h tới để điều chỉnh lịch làm mát.
3. Ước tính mức tiết kiệm chi phí nếu tối ưu setpoint chiller."""
        return reply, tools_called

copilot_orchestrator = CopilotOrchestrator()
