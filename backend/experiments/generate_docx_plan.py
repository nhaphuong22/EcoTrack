import os
import docx
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

def set_cell_background(cell, hex_color):
    """Đặt màu nền cho ô trong bảng."""
    shading_elm = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    cell._tc.get_or_add_tcPr().append(shading_elm)

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    """Đặt lề trong ô bảng."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for m, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        node = OxmlElement(f'w:{m}')
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)

def create_task_allocation_document(output_path: str):
    doc = Document()

    # Thiết lập lề trang chuẩn A4
    for section in doc.sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.85)
        section.right_margin = Inches(0.85)

    # Bảng màu chủ đạo (EcoTrack Brand Colors)
    COLOR_PRIMARY = RGBColor(15, 76, 129)     # Deep Tech Navy (#0F4C81)
    COLOR_SECONDARY = RGBColor(16, 149, 124)  # Eco Green/Teal (#10957C)
    COLOR_DARK = RGBColor(30, 41, 59)         # Slate Dark (#1E293B)
    COLOR_MUTED = RGBColor(100, 116, 139)     # Slate Muted (#64748B)

    # 1. HEADER DỰ ÁN
    p_header = doc.add_paragraph()
    p_header.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_brand = p_header.add_run("DỰ ÁN ECOTRACK — HỆ THỐNG QUẢN LÝ NĂNG LƯỢNG TÒA NHÀ THÔNG MINH\n")
    run_brand.font.name = "Arial"
    run_brand.font.size = Pt(11)
    run_brand.font.bold = True
    run_brand.font.color.rgb = COLOR_SECONDARY

    run_title = p_header.add_run("KẾ HOẠCH HÀNH ĐỘNG VÀ PHÂN CÔNG NHIỆM VỤ CHI TIẾT\n")
    run_title.font.name = "Arial"
    run_title.font.size = Pt(18)
    run_title.font.bold = True
    run_title.font.color.rgb = COLOR_PRIMARY

    run_sub = p_header.add_run("Giai đoạn nước rút 10 tuần: Bảo vệ Đồ án (15/12/2026) & Chuẩn bị Bài báo Khoa học")
    run_sub.font.name = "Arial"
    run_sub.font.size = Pt(11)
    run_sub.font.italic = True
    run_sub.font.color.rgb = COLOR_MUTED

    doc.add_paragraph() # Spacing

    # 2. HỘP THÔNG TIN TỔNG QUAN (CALLOUT BOX)
    info_table = doc.add_table(rows=1, cols=1)
    info_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = info_table.cell(0, 0)
    set_cell_background(cell, "F0FDF4") # Light green tint
    set_cell_margins(cell, top=140, bottom=140, left=200, right=200)

    p_info = cell.paragraphs[0]
    p_info.add_run("📌 THÔNG TIN ĐIỀU HÀNH DỰ ÁN:\n").bold = True
    p_info.runs[0].font.color.rgb = COLOR_SECONDARY
    p_info.runs[0].font.size = Pt(10.5)

    bullets = [
        ("Thời gian thực hiện:", " Từ 05/10/2026 đến 15/12/2026 (Thời lượng: 10 tuần)."),
        ("Mốc Review Môn học:", " Ngày 15/12/2026 (Bảo vệ trước Hội đồng Khoa/Viện)."),
        ("Mục tiêu kép:", " Vừa ra mắt sản phẩm hoàn chỉnh đạt điểm A+, vừa hoàn thành bản thảo bài báo khoa học chuẩn IEEE."),
        ("Quy mô nhóm:", " 5 thành viên (Phương, Quân, Thành viên 3, Thành viên 4, Thành viên 5)."),
        ("Cập nhật tiến độ lõi:", " Phân hệ Data Pipeline (Phương) và AI/ML Models (Quân) đã hoàn thành xuất sắc 100% phần cốt lõi.")
    ]
    for b_title, b_desc in bullets:
        p_b = cell.add_paragraph()
        p_b.paragraph_format.left_indent = Inches(0.15)
        p_b.paragraph_format.space_after = Pt(2)
        r_t = p_b.add_run(f"• {b_title}")
        r_t.bold = True
        r_t.font.size = Pt(10)
        r_d = p_b.add_run(b_desc)
        r_d.font.size = Pt(10)

    doc.add_paragraph()

    # 3. ĐÁNH GIÁ HIỆN TRẠNG & ĐIỂM SÁNG
    h1 = doc.add_paragraph()
    r_h1 = h1.add_run("I. ĐÁNH GIÁ HIỆN TRẠNG VÀ CƠ SỞ KỸ THUẬT SẴN CÓ")
    r_h1.font.name = "Arial"
    r_h1.font.size = Pt(13)
    r_h1.font.bold = True
    r_h1.font.color.rgb = COLOR_PRIMARY

    p_stat = doc.add_paragraph()
    p_stat.add_run(
        "Nhờ sự hoàn thành kịp thời và chuẩn chỉ của Thành viên 1 (Phương) và Thành viên 2 (Quân), "
        "dự án EcoTrack hiện tại đã sở hữu hai trụ cột quan trọng nhất của hệ thống BEMS thông minh:\n"
    )

    p_stat_items = [
        ("Thành viên 1 — Phương (Data Pipeline Lead): ", 
         "Đã hoàn thiện module nạp dữ liệu chuẩn Building Data Genome 2 (BDG2), làm sạch chuỗi thời gian, xử lý yếu tố khí tượng (nhiệt độ, độ ẩm) và xây dựng bộ dữ liệu mô phỏng gồm 3 sự cố mẫu có nhãn chuẩn."),
        ("Thành viên 2 — Quân (AI/ML Lead): ", 
         "Đã huấn luyện, tối ưu và lưu trữ checkpoint thực tế của mô hình dự báo XGBoost (MAPE đạt 8.42%, R2 = 0.912) và mô hình phát hiện dị thường Isolation Forest kết hợp phân tích độ lệch dư (Residual Analysis)."),
        ("Hạ tầng kiểm nghiệm học thuật (Vừa được kích hoạt): ", 
         "Đã thiết lập module ExperimentLogger ghi log thực nghiệm tự động và bộ benchmark 4 Case Study để đo lường độ chính xác chẩn đoán của Agent.")
    ]
    for name, desc in p_stat_items:
        p_i = doc.add_paragraph()
        p_i.paragraph_format.left_indent = Inches(0.2)
        r_name = p_i.add_run(f"✅ {name}")
        r_name.bold = True
        r_name.font.size = Pt(10.5)
        r_desc = p_i.add_run(desc)
        r_desc.font.size = Pt(10.5)

    doc.add_paragraph()

    # 4. BẢNG PHÂN CÔNG NHIỆM VỤ CHO TỪNG THÀNH VIÊN
    h2 = doc.add_paragraph()
    r_h2 = h2.add_run("II. BẢNG PHÂN CÔNG NHIỆM VỤ NƯỚC RÚT CHO 5 THÀNH VIÊN")
    r_h2.font.name = "Arial"
    r_h2.font.size = Pt(13)
    r_h2.font.bold = True
    r_h2.font.color.rgb = COLOR_PRIMARY

    # Tạo bảng phân công chuyên nghiệp
    table = doc.add_table(rows=1, cols=4)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False

    # Định dạng header bảng
    hdr_cells = table.rows[0].cells
    headers = ["Thành viên & Vai trò", "Nhiệm vụ Hệ thống (Track 1)", "Nhiệm vụ NCKH / Báo cáo (Track 2)", "Deadline & Sản phẩm bàn giao"]
    col_widths = [Inches(1.5), Inches(2.2), Inches(1.8), Inches(1.5)]

    for idx, text in enumerate(headers):
        hdr_cells[idx].width = col_widths[idx]
        p = hdr_cells[idx].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(text)
        r.bold = True
        r.font.size = Pt(10)
        r.font.color.rgb = RGBColor(255, 255, 255)
        set_cell_background(hdr_cells[idx], "0F4C81") # Primary Navy
        set_cell_margins(hdr_cells[idx], top=120, bottom=120, left=100, right=100)

    # Dữ liệu 5 thành viên
    members_data = [
        (
            "Thành viên 1:\nPHƯƠNG\n(Data Pipeline Lead)",
            "• Đóng gói dữ liệu mẫu BDG2 thành SQLite/JSON ổn định.\n• Xây dựng script giả lập đẩy dữ liệu thời gian thực (Real-time Stream Simulator).\n• Tối ưu tốc độ ETL nạp chuỗi thời gian.",
            "• Chịu trách nhiệm viết Mục III.1 (Data Engineering & BDG2 Features) trong báo cáo khoa học.\n• Cung cấp thống kê mô tả (Mean, Variance, Cyclical Trends) của tập dữ liệu.",
            "Tuần 4 (25/10)\n➔ File database nạp sẵn dữ liệu\n➔ Script streaming simulator\n➔ Mục III.1 bản thảo bài báo"
        ),
        (
            "Thành viên 2:\nQUÂN\n(AI/ML Lead)",
            "• Hỗ trợ TV3 và TV4 đóng gói API suy luận (Inference Wrapper) cho XGBoost và Isolation Forest.\n• Tối ưu thời gian inference < 20ms/mẫu.\n• Cung cấp confidence intervals (khoảng tin cậy 95%).",
            "• Chịu trách nhiệm viết Mục III.2, III.3 và IV.2, IV.3 trong bài báo.\n• Chạy thí nghiệm so sánh đối chuẩn (XGBoost vs RF, LSTM; Isolation Forest vs SVM, LOF).\n• Vẽ biểu đồ sai số và ROC curve.",
            "Tuần 5 (01/11)\n➔ Module Predictor tối ưu\n➔ Bảng số liệu benchmark baselines\n➔ Biểu đồ phân tích độ lệch dư"
        ),
        (
            "Thành viên 3:\nTHÀNH VIÊN 3\n(Backend & Data Services)",
            "• Xây dựng cơ chế In-memory Caching (TTL Cache / Redis) tại router energy.py để API phản hồi tức thì (<50ms).\n• Xây dựng API quản lý trạng thái Anomaly (Open ➔ Acknowledged ➔ Resolved).\n• Đảm bảo toàn bộ REST API đạt chuẩn OpenAPI/Swagger.",
            "• Viết Mục V (Hạ tầng dịch vụ & Hiệu năng API Backend).\n• Đo đạc độ trễ API (Latency benchmarks) khi chịu tải đồng thời (Concurrent requests) để đưa vào báo cáo.",
            "Tuần 6 (08/11)\n➔ Backend Caching hoàn chỉnh\n➔ Bộ API quản lý sự cố (/anomalies/status)\n➔ Bảng đo đạc tải API"
        ),
        (
            "Thành viên 4:\nTHÀNH VIÊN 4\n(AI Agent & LLM Lead)",
            "• Nâng cấp CopilotOrchestrator lên Native Function Calling (Google Gemini API / OpenAI API).\n• Cấu hình Context Injection khi kỹ sư nhấp vào sự cố cụ thể trên UI.\n• Tối ưu hóa prompt kỹ thuật điện và cơ chế chống ảo giác (Grounded RCA).",
            "• Viết Mục III.4 và IV.4 (Tác tử LLM & Đo lường độ bám sát dữ liệu).\n• Sử dụng run_benchmark.py để kiểm thử và ghi log 4 Case Study sự cố.\n• Thống kê tỷ lệ chọn đúng tool và độ chính xác chẩn đoán nguyên nhân gốc.",
            "Tuần 7 (15/11)\n➔ Function Calling Agent chạy mượt\n➔ Bộ log thực nghiệm agent_eval_logs.jsonl\n➔ Thống kê độ chính xác RCA"
        ),
        (
            "Thành viên 5:\nTHÀNH VIÊN 5\n(Frontend Lead & Project Manager)",
            "• Nâng cấp giao diện React Dashboard (vẽ dải màu 95% tin cậy, ghim chấm đỏ nhấp nháy tại các điểm sự cố).\n• Tích hợp thanh trượt Zoom/Brush trên biểu đồ Recharts.\n• Kết nối tương tác 2 chiều mượt mà giữa Anomaly Table và Copilot Drawer.\n• Đóng gói Docker Compose chạy 1 lệnh.",
            "• Viết Mục V (Nghiên cứu trường hợp & Trực quan hóa tương tác người - máy).\n• Chụp ảnh giao diện, thiết kế sơ đồ kiến trúc vector chuẩn IEEE.\n• Quản lý tài liệu Overleaf và điều phối tiến độ toàn nhóm.",
            "Tuần 8 (22/11)\n➔ Bản quyền giao diện Dashboard v1.0\n➔ Docker Compose hoàn chỉnh\n➔ Video demo backup 3 phút"
        )
    ]

    for row_idx, data in enumerate(members_data):
        row = table.add_row()
        bg_color = "F8FAFC" if row_idx % 2 == 1 else "FFFFFF"
        for c_idx, cell in enumerate(row.cells):
            cell.width = col_widths[c_idx]
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            r = p.add_run(data[c_idx])
            r.font.size = Pt(9.5)
            if c_idx == 0:
                r.bold = True
                r.font.color.rgb = COLOR_PRIMARY
            set_cell_background(cell, bg_color)
            set_cell_margins(cell, top=100, bottom=100, left=100, right=100)

    doc.add_paragraph()

    # 5. LỘ TRÌNH 3 GIAI ĐOẠN TỪ NAY ĐẾN 15/12/2026
    h3 = doc.add_paragraph()
    r_h3 = h3.add_run("III. LỘ TRÌNH THỰC HIỆN 10 TUẦN NƯỚC RÚT")
    r_h3.font.name = "Arial"
    r_h3.font.size = Pt(13)
    r_h3.font.bold = True
    r_h3.font.color.rgb = COLOR_PRIMARY

    phases = [
        ("Chặng 1: Tối ưu Lõi & Hạ tầng API (Tuần 1 - Tuần 3 | 05/10 - 25/10)",
         "Tập trung Thành viên 3 và 4: Cài đặt bộ đệm Caching, nâng cấp Copilot Function Calling, kết nối với model đã có của Quân và dữ liệu của Phương."),
        ("Chặng 2: Ghép nối Fullstack & Giao diện Dashboard (Tuần 4 - Tuần 6 | 26/10 - 15/11)",
         "Tập trung Thành viên 5: Nối toàn diện React với FastAPI, hoàn thiện Copilot Drawer, hoàn thành kịch bản click vào sự cố mở chẩn đoán."),
        ("Chặng 3: Thử nghiệm Benchmark & Thu thập số liệu (Tuần 7 - Tuần 8 | 16/11 - 29/11)",
         "Toàn nhóm chạy thực nghiệm trên bộ 4 Case Study, ghi lại toàn bộ log thực nghiệm vào agent_eval_logs.jsonl để hoàn thiện các bảng số liệu khoa học."),
        ("Chặng 4: Tổng duyệt Demo & Bảo vệ Đồ án (Tuần 9 - Tuần 10 | 30/11 - 15/12)",
         "Đóng gói Docker Compose (docker-compose up --build), quay video demo dự phòng, tổng duyệt thuyết trình và nộp báo cáo hoàn chỉnh vào ngày 15/12/2026.")
    ]
    for p_title, p_desc in phases:
        p_ph = doc.add_paragraph()
        p_ph.paragraph_format.left_indent = Inches(0.2)
        r_pt = p_ph.add_run(f"🚩 {p_title}\n")
        r_pt.bold = True
        r_pt.font.color.rgb = COLOR_SECONDARY
        r_pt.font.size = Pt(10.5)
        r_pd = p_ph.add_run(p_desc)
        r_pd.font.size = Pt(10)

    doc.add_paragraph()

    # 6. MẪU EMAIL THÔNG BÁO CHO NHÓM
    h4 = doc.add_paragraph()
    r_h4 = h4.add_run("IV. MẪU TIN NHẮN / EMAIL GỬI ĐỒNG BỘ ĐẾN CÁC THÀNH VIÊN")
    r_h4.font.name = "Arial"
    r_h4.font.size = Pt(13)
    r_h4.font.bold = True
    r_h4.font.color.rgb = COLOR_PRIMARY

    box_email = doc.add_table(rows=1, cols=1)
    box_email.alignment = WD_TABLE_ALIGNMENT.CENTER
    c_email = box_email.cell(0, 0)
    set_cell_background(c_email, "F8FAFC")
    set_cell_margins(c_email, top=120, bottom=120, left=150, right=150)
    p_em = c_email.paragraphs[0]
    
    email_text = """Tiêu đề: [EcoTrack] Kế hoạch phân công nhiệm vụ 10 tuần nước rút (Review ngày 15/12/2026)

Chào các thành viên nhóm EcoTrack,

Hiện tại, nhóm chúng ta đã hoàn thành xuất sắc 100% phần việc cốt lõi của phân hệ Data Pipeline (Phương phụ trách) và phân hệ AI/ML Forecaster & Anomaly Detector (Quân phụ trách). Các mô hình XGBoost và Isolation Forest đã được train và lưu trữ checkpoint hoàn chỉnh.

Để chuẩn bị chu đáo nhất cho buổi Review đồ án môn học vào ngày 15/12/2026 và hướng tới mục tiêu hoàn thiện bài báo khoa học chuẩn IEEE, nhóm trưởng gửi bản kế hoạch hành động và phân công nhiệm vụ chi tiết đính kèm trong file: KE_HOACH_PHAN_CONG_NHIEM_VU_ECOTRACK.docx.

Mọi người vui lòng mở file, kiểm tra phần việc, checklist và deadline bàn giao của mình:
- Phương (TV1): Data SQLite & Streaming Simulation + Mục Data bài báo.
- Quân (TV2): Inference Wrapper tối ưu + Thí nghiệm đối chuẩn ML.
- Thành viên 3: In-memory Caching Backend + API trạng thái sự cố.
- Thành viên 4: Native Function Calling Gemini/OpenAI + Đo đạc độ bám sát dữ liệu RCA.
- Thành viên 5: React Dashboard tương tác cao + Docker Compose + Quản lý tài liệu Overleaf.

Tài liệu bản thảo bài báo khoa học đã được soạn thảo sẵn tại docs/ECOTRACK_SCIENTIFIC_REPORT_DRAFT.md để cả nhóm cùng theo dõi.
Chúc nhóm chúng ta phối hợp thật tốt và đạt kết quả A+ trong đợt bảo vệ 15/12 tới!"""

    r_em = p_em.add_run(email_text)
    r_em.font.size = Pt(9.5)
    r_em.font.name = "Calibri"

    # Lưu file
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    doc.save(output_path)
    print(f"Document successfully created at: {output_path}")

if __name__ == "__main__":
    target = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "KE_HOACH_PHAN_CONG_NHIEM_VU_ECOTRACK.docx")
    create_task_allocation_document(target)
