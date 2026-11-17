import os
import json
import time
import logging
import asyncio
from typing import Dict, Any, List, Tuple, AsyncGenerator
from src.config import (
    get_tariff_rate_usd,
    get_tariff_rate_vnd,
    get_gemini_model,
    get_openai_model,
)
from src.agent.prompts import SYSTEM_PROMPT
from src.agent.tools.energy_tools import (
    query_metrics,
    get_anomalies,
    query_forecast_summary,
    calculate_waste_cost,
)
from src.agent.experiment_logger import experiment_logger

logger = logging.getLogger("ecotrack.copilot")


class CopilotOrchestrator:
    def __init__(self):
        self.gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.openai_key = os.getenv("OPENAI_API_KEY", "").strip()

    def _resolve_tool_calls(
        self, user_message: str, history: List[Dict[str, Any]] = None
    ) -> Tuple[List[str], Dict[str, Any], List[Dict[str, Any]], str]:
        """
        Determines which tools to call based on the user query and prior conversation history.
        Returns: (tools_called, tool_data, sources, context_str)
        """
        tools_called = []
        sources = []
        msg_lower = user_message.lower().strip()
        tool_data = {
            "metrics": None,
            "anomalies": None,
            "forecast": None,
            "waste_cost": None,
            "knowledge": None,
        }

        # Check conversation history for follow-up context (Story 3.3)
        recent_history = (history or [])[-10:]
        prior_context = ""
        if recent_history:
            last_turn = recent_history[-1]
            prior_context = str(last_turn.get("content", "")).lower()

        # Check if query is a follow-up without explicit entities
        is_follow_up = any(
            phrase in msg_lower
            for phrase in [
                "còn nguyên nhân nào",
                "nguyên nhân khác",
                "tại sao",
                "khắc phục thế nào",
                "làm gì để khắc phục",
                "chi tiết hơn",
                "giải thích thêm",
                "nữa không",
            ]
        ) or (len(msg_lower.split()) <= 6 and ("nào" in msg_lower or "sao" in msg_lower or "thế" in msg_lower))

        # 1. Anomaly diagnosis
        is_anomaly_query = any(
            w in msg_lower for w in ["bất thường", "sự cố", "anomaly", "anomalies", "lỗi", "chẩn đoán", "nguyên nhân"]
        ) or (is_follow_up and any(w in prior_context for w in ["bất thường", "sự cố", "anomaly", "chẩn đoán"]))

        if is_anomaly_query:
            try:
                tool_data["anomalies"] = get_anomalies(limit=3)
                tools_called.append("get_anomalies")
            except Exception as err:
                logger.warning(f"[Copilot] Tool get_anomalies failed: {err}")

        # 2. Forecast inquiry
        is_forecast_query = any(
            w in msg_lower for w in ["dự báo", "forecast", "ngày mai", "đỉnh", "peak", "24h", "tải đỉnh"]
        ) or (is_follow_up and any(w in prior_context for w in ["dự báo", "forecast", "đỉnh"]))

        if is_forecast_query:
            try:
                tool_data["forecast"] = query_forecast_summary()
                tools_called.append("query_forecast_summary")
            except Exception as err:
                logger.warning(f"[Copilot] Tool query_forecast_summary failed: {err}")

        # 3. Cost calculation
        if any(w in msg_lower for w in ["chi phí", "tiền", "lãng phí", "cost", "vnd", "usd", "tiền điện"]):
            tools_called.append("calculate_waste_cost")

        # 4. Metrics overview
        is_metrics_query = any(
            w in msg_lower for w in ["tổng quan", "tiêu thụ", "kwh", "chỉ số", "metrics", "bao nhiêu điện"]
        )
        if is_metrics_query and not is_anomaly_query and not is_forecast_query:
            try:
                tool_data["metrics"] = query_metrics()
                tools_called.append("query_metrics")
            except Exception as err:
                logger.warning(f"[Copilot] Tool query_metrics failed: {err}")

        # 5. Domain Knowledge (RAG) - Story 3.2
        # Check if query is ONLY about live metrics (exclude knowledge retrieval)
        is_pure_live_metrics = is_metrics_query and not any(
            w in msg_lower
            for w in [
                "tiêu chuẩn", "qcvn", "evn", "biểu giá", "giờ cao điểm", "giờ thấp điểm",
                "chiller", "hvac", "vav", "setpoint", "tiết kiệm", "quy chuẩn", "định mức",
                "hướng dẫn", "cop", "lpd", "làm mát", "thông gió"
            ]
        )

        is_knowledge_query = any(
            w in msg_lower
            for w in [
                "tiêu chuẩn", "qcvn", "evn", "biểu giá", "biểu giá điện", "giờ cao điểm",
                "giờ thấp điểm", "chiller", "hvac", "vav", "setpoint", "tiết kiệm",
                "quy chuẩn", "hướng dẫn", "định mức", "lpd", "cop", "nhiệt độ", "làm mát",
                "thông gió", "giá điện", "biện pháp", "khuyến nghị"
            ]
        ) or (not is_anomaly_query and not is_forecast_query and not is_pure_live_metrics)

        if is_knowledge_query and not is_pure_live_metrics:
            try:
                from src.rag.retriever import query_knowledge
                chunks = query_knowledge(user_message, k=3)
                if chunks:
                    tools_called.append("domain_knowledge")
                    tool_data["knowledge"] = chunks
                    sources = [
                        {
                            "title": c.get("title", ""),
                            "source": c.get("source", ""),
                            "snippet": c.get("snippet", ""),
                        }
                        for c in chunks
                    ]
            except Exception as err:
                logger.warning(f"[Copilot] Knowledge base / vector store unavailable, skipping RAG: {err}")

        # Build context string
        context_parts = []
        if tool_data["metrics"]:
            context_parts.append(f"[Dữ liệu Tool query_metrics]: {json.dumps(tool_data['metrics'], ensure_ascii=False)}")
        if tool_data["anomalies"]:
            context_parts.append(f"[Dữ liệu Tool get_anomalies]: {json.dumps(tool_data['anomalies'], ensure_ascii=False)}")
        if tool_data["forecast"]:
            context_parts.append(f"[Dữ liệu Tool query_forecast_summary]: {json.dumps(tool_data['forecast'], ensure_ascii=False)}")
        if tool_data["knowledge"]:
            kb_str = "\n".join([f"- ({c.get('source', '')}) {c.get('title', '')}: {c.get('snippet', '')}" for c in tool_data["knowledge"]])
            context_parts.append(f"[Tài liệu tham khảo chuyên ngành (RAG)]:\n{kb_str}")

        context_str = "\n".join(context_parts)
        return tools_called, tool_data, sources, context_str

    def process_chat(
        self, user_message: str, history: List[Dict[str, Any]] = None
    ) -> Tuple[str, List[str], List[Dict[str, Any]], str]:
        """
        Processes a chat turn using Cloud LLM or rule-based tool dispatch fallback.
        Returns: (assistant_response_markdown, list_of_tools_called, sources, engine)
        """
        start_time = time.time()
        tools_called, tool_data, sources, context_str = self._resolve_tool_calls(user_message, history)
        recent_history = (history or [])[-10:]
        reply = ""
        engine = "heuristic"

        gemini_model = get_gemini_model()
        openai_model = get_openai_model()

        # Step 2: Try Cloud API if keys are provided
        if self.gemini_key:
            try:
                from google import genai
                client = genai.Client(api_key=self.gemini_key)

                # Build prompt with history
                history_text = ""
                if recent_history:
                    lines = [f"{turn.get('role', 'user')}: {turn.get('content', '')}" for turn in recent_history]
                    history_text = "\n[Lịch sử hội thoại trước đó]:\n" + "\n".join(lines) + "\n"

                prompt = f"{SYSTEM_PROMPT}\n{history_text}\n{context_str}\n\nNgười dùng: {user_message}"
                response = client.models.generate_content(
                    model=gemini_model,
                    contents=prompt
                )
                if response and response.text:
                    reply = response.text
                    engine = "gemini"
            except Exception as err:
                logger.warning(f"[Copilot] Gemini provider failed ({gemini_model}): {err}")

        if not reply and self.openai_key:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=self.openai_key)

                messages = [{"role": "system", "content": SYSTEM_PROMPT}]
                if context_str:
                    messages.append({"role": "system", "content": f"[Dữ liệu bối cảnh hệ thống]:\n{context_str}"})

                for turn in recent_history:
                    role = turn.get("role", "user")
                    if role in ("user", "assistant"):
                        messages.append({"role": role, "content": turn.get("content", "")})

                messages.append({"role": "user", "content": user_message})

                response = client.chat.completions.create(
                    model=openai_model,
                    messages=messages
                )
                if response.choices:
                    reply = response.choices[0].message.content
                    engine = "openai"
            except Exception as err:
                logger.warning(f"[Copilot] OpenAI provider failed ({openai_model}): {err}")

        # Step 3: Heuristic domain reasoning fallback
        if not reply:
            reply, tools_called = self._generate_heuristic_response(
                user_message,
                tool_data["metrics"],
                tool_data["anomalies"],
                tool_data["forecast"],
                tool_data["knowledge"],
                tools_called,
            )
            engine = "heuristic"

        # Log turn for evaluation
        latency_ms = (time.time() - start_time) * 1000
        experiment_logger.log_interaction(
            user_message=user_message,
            response_text=reply,
            tools_called=tools_called,
            latency_ms=latency_ms,
            model_name=engine
        )

        return reply, tools_called, sources, engine

    async def stream_chat(
        self, user_message: str, history: List[Dict[str, Any]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Streams a chat response token-by-token over Server-Sent Events.
        Yields:
          {"type": "token", "token": "..."}
          {"type": "sources", "sources": [...], "tools_used": [...], "engine": "..."}
          {"type": "done", "reply": "..."}
        """
        tools_called, tool_data, sources, context_str = self._resolve_tool_calls(user_message, history)
        recent_history = (history or [])[-10:]
        gemini_model = get_gemini_model()
        openai_model = get_openai_model()
        engine = "heuristic"
        full_reply = ""
        stream_successful = False

        # Attempt Gemini streaming
        if self.gemini_key:
            try:
                from google import genai
                client = genai.Client(api_key=self.gemini_key)

                history_text = ""
                if recent_history:
                    lines = [f"{turn.get('role', 'user')}: {turn.get('content', '')}" for turn in recent_history]
                    history_text = "\n[Lịch sử hội thoại trước đó]:\n" + "\n".join(lines) + "\n"

                prompt = f"{SYSTEM_PROMPT}\n{history_text}\n{context_str}\n\nNgười dùng: {user_message}"

                response_stream = client.models.generate_content_stream(
                    model=gemini_model,
                    contents=prompt
                )
                engine = "gemini"
                for chunk in response_stream:
                    if chunk.text:
                        full_reply += chunk.text
                        yield {"type": "token", "token": chunk.text}
                stream_successful = True
            except Exception as err:
                logger.warning(f"[Copilot] Gemini streaming failed ({gemini_model}): {err}")
                if full_reply:
                    yield {"type": "error", "error": f"Gemini stream interrupted: {err}"}
                    return

        # Attempt OpenAI streaming
        if not stream_successful and self.openai_key:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=self.openai_key)

                messages = [{"role": "system", "content": SYSTEM_PROMPT}]
                if context_str:
                    messages.append({"role": "system", "content": f"[Dữ liệu bối cảnh]:\n{context_str}"})

                for turn in recent_history:
                    role = turn.get("role", "user")
                    if role in ("user", "assistant"):
                        messages.append({"role": role, "content": turn.get("content", "")})
                messages.append({"role": "user", "content": user_message})

                response_stream = client.chat.completions.create(
                    model=openai_model,
                    messages=messages,
                    stream=True
                )
                engine = "openai"
                for chunk in response_stream:
                    delta = chunk.choices[0].delta.content if chunk.choices else ""
                    if delta:
                        full_reply += delta
                        yield {"type": "token", "token": delta}
                stream_successful = True
            except Exception as err:
                logger.warning(f"[Copilot] OpenAI streaming failed ({openai_model}): {err}")
                if full_reply:
                    yield {"type": "error", "error": f"OpenAI stream interrupted: {err}"}
                    return

        # Fallback to chunked heuristic generation
        if not stream_successful:
            engine = "heuristic"
            heuristic_reply, tools_called = self._generate_heuristic_response(
                user_message,
                tool_data["metrics"],
                tool_data["anomalies"],
                tool_data["forecast"],
                tool_data["knowledge"],
                tools_called,
            )
            full_reply = heuristic_reply
            # Stream words/lines in small chunks for smooth typing effect (< 2.5s)
            chunks = heuristic_reply.split(" ")
            for i, chunk in enumerate(chunks):
                token = chunk + (" " if i < len(chunks) - 1 else "")
                yield {"type": "token", "token": token}
                await asyncio.sleep(0.015)

        # Emit sources and tools metadata event
        yield {
            "type": "sources",
            "sources": sources,
            "tools_used": tools_called,
            "engine": engine,
        }

        # Emit done event
        yield {
            "type": "done",
            "reply": full_reply,
        }

    def _generate_heuristic_response(
        self, query: str, metrics, anomalies, forecast, knowledge, tools_called
    ) -> Tuple[str, List[str]]:
        msg = query.lower()

        # 1. Anomaly response
        if any(w in msg for w in ["bất thường", "sự cố", "chẩn đoán", "anom"]):
            if not anomalies:
                try:
                    anomalies = get_anomalies(limit=3)
                    if "get_anomalies" not in tools_called:
                        tools_called.append("get_anomalies")
                except Exception:
                    pass

            top_anom = anomalies[-1] if anomalies else None
            if top_anom:
                reply = f"""### 🔍 Chẩn đoán sự cố bất thường ({top_anom['id']})

- 📌 **Thời điểm ghi nhận**: `{top_anom['timestamp']}`
- ⚡ **Tiêu thụ thực tế**: **{top_anom['actual_kwh']} kWh** (Baseline dự báo: {top_anom['predicted_kwh']} kWh, chênh lệch **+{top_anom['delta_kwh']} kWh**)
- 🌡️ **Nhiệt độ ngoài trời**: {top_anom['outdoor_temp_c']}°C | **Mức độ**: `{top_anom['severity']}` (Điểm Anomaly: {top_anom['anomaly_score']})

#### 🔎 Phân tích nguyên nhân gốc rễ (RCA)
1. **Lệch pha chu kỳ**: Sự cố xảy ra ngoài giờ vận hành chính (Building unoccupied), nhưng phụ tải chiller và quạt thông gió vẫn duy trì ở công suất tương đương giờ cao điểm.
2. **Nguyên nhân tiềm ẩn**: {top_anom['reason']}.
3. **Tổn thất chi phí**: Ước tính gây lãng phí khoảng **{top_anom['delta_kwh'] * get_tariff_rate_vnd():,.0f} VNĐ** (~${top_anom['delta_kwh'] * get_tariff_rate_usd():.2f} USD) cho mỗi giờ duy trì sự cố.

#### 💡 Khuyến nghị cho Kỹ sư vận hành
- [ ] Kiểm tra actuator và van damper gió tươi tại buồng AHU tầng kỹ thuật.
- [ ] Xác minh trạng thái override thủ công trên giao diện BMS trung tâm.
- [ ] Đặt lại lịch hẹn giờ tắt chiller trước 19:00 đối với các khu vực văn phòng cho thuê."""
                return reply, tools_called

        # 2. Forecast response
        if any(w in msg for w in ["dự báo", "forecast", "ngày mai", "đỉnh", "peak"]):
            if not forecast:
                try:
                    forecast = query_forecast_summary()
                    if "query_forecast_summary" not in tools_called:
                        tools_called.append("query_forecast_summary")
                except Exception:
                    pass
            if forecast:
                reply = f"""### 📈 Báo cáo dự báo phụ tải điện 24h tới (XGBoost Engine)

- ⚡ **Công suất đỉnh dự kiến**: **{forecast['expected_peak_kw']} kW** tại thời điểm `{forecast['peak_timestamp']}`.
- 📊 **Tiêu thụ trung bình**: **{forecast['average_forecast_kwh']} kWh/giờ**.
- 🎯 **Dải tin cậy 95%**: `{forecast['confidence_interval_95']}` (theo mô hình chuỗi thời gian).

#### 💡 Khuyến nghị tối ưu biểu giá điện (Peak Shaving)
- Thực hiện **Pre-cooling (làm mát sớm)** trước khung giờ 13:00 - 15:30 khoảng 1.5 giờ khi biểu giá điện còn ở mức bình thường để giảm 15-20% công suất đỉnh giờ cao điểm."""
                return reply, tools_called

        # 3. Knowledge / RAG response
        if knowledge and len(knowledge) > 0:
            top_k = knowledge[0]
            other_sources = "\n".join([f"- **{k.get('title', '')}** (`{k.get('source', '')}`)" for k in knowledge])
            reply = f"""### 📚 Tư vấn kỹ thuật & quy chuẩn năng lượng ({top_k.get('title', 'Tài liệu kỹ thuật')})

Dựa trên tài liệu tham khảo **{top_k.get('title', '')}** ({top_k.get('source', '')}):

{top_k.get('snippet', '')}

#### 💡 Khuyến nghị vận hành & tuân thủ:
- Áp dụng các định mức và khung giờ biểu giá quy định để tối ưu hóa chi phí điện năng tòa nhà.
- Đối chiếu công suất thiết kế với tiêu chuẩn QCVN 09:2017/BXD nhằm tránh vượt tải định mức.

**Tài liệu liên quan được tra cứu:**
{other_sources}"""
            return reply, tools_called

        # 4. Default overview summary
        if not metrics:
            try:
                metrics = query_metrics()
                if "query_metrics" not in tools_called:
                    tools_called.append("query_metrics")
            except Exception:
                metrics = {
                    "building_id": "office_tower_01",
                    "total_consumption_kwh": 0.0,
                    "baseline_kwh": 0.0,
                    "peak_demand_kw": 0.0,
                    "anomalies_detected": 0,
                    "estimated_waste_vnd": 0,
                    "estimated_waste_usd": 0,
                }

        reply = f"""### 🏢 Báo cáo tổng quan năng lượng EcoTrack ({metrics['building_id']})

- ⚡ **Tổng điện năng tiêu thụ (30 ngày)**: **{metrics['total_consumption_kwh']:,.1f} kWh** (Đường cơ sở: {metrics['baseline_kwh']:,.1f} kWh)
- 🚀 **Công suất đỉnh (Peak Demand)**: **{metrics['peak_demand_kw']} kW**
- ⚠️ **Số điểm bất thường phát hiện**: **{metrics['anomalies_detected']} điểm** (Isolation Forest)
- 💸 **Ước tính lãng phí tích lũy**: **{metrics['estimated_waste_vnd']:,.0f} VNĐ** (~${metrics['estimated_waste_usd']:,.2f} USD)

Tôi có thể giúp anh/chị:
1. Phân tích chi tiết từng sự cố bất thường gần nhất.
2. Đánh giá biểu đồ phụ tải dự báo trong 24h tới để điều chỉnh lịch làm mát.
3. Tra cứu quy chuẩn QCVN 09:2017/BXD và biểu giá EVN."""
        return reply, tools_called


copilot_orchestrator = CopilotOrchestrator()
