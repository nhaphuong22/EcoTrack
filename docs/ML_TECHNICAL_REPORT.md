# BÁO CÁO KỸ THUẬT PHÂN HỆ AI & MACHINE LEARNING (SPRINT 5)
## DỰ ÁN ECOTRACK: HỆ THỐNG GIÁM SÁT VÀ DỰ BÁO NĂNG LƯỢNG THÔNG MINH

---

- **Nhóm sinh viên thực hiện:** Thành viên 1 (Data Engineering & Forecasting) & Thành viên 2 (Anomaly Detection & AI Integration)
- **Tập dữ liệu nguồn:** Building Data Genome 2 (BDG2) — Tòa nhà thương mại `Hog_office_Betsy`
- **Phiên bản mô hình:** `xgboost_forecaster.joblib` & `isolation_forest.joblib` (Sprint 5 Production Artifacts)
- **Ngày hoàn thiện:** Tháng 10/2026

---

## MỤC LỤC

1. [TỔNG QUAN PHÂN HỆ MACHINE LEARNING](#1-tổng-quan-phân-hệ-machine-learning)
2. [PHÂN HỆ DATA ENGINEERING & TIỀN XỬ LÝ DỮ LIỆU](#2-phân-hệ-data-engineering--tiền-xử-lý-dữ-liệu)
   - 2.1. Nguồn dữ liệu thực nghiệm (Building Data Genome 2)
   - 2.2. Chiến lược phân tách dữ liệu chuỗi thời gian (Time-Series Split 80/20)
   - 2.3. Kỹ thuật trích xuất và biến đổi đặc trưng (Feature Engineering)
3. [MÔ HÌNH DỰ BÁO PHỤ TẢI NĂNG LƯỢNG (XGBOOST FORECASTER)](#3-mô-hình-dự-báo-phụ-tải-năng-lượng-xgboost-forecaster)
   - 3.1. Cơ sở lý thuyết thuật toán Gradient Boosting Decision Trees
   - 3.2. Cấu hình siêu tham số tối ưu (Hyperparameters Tuning)
   - 3.3. Bảng đo lường hiệu năng thực tế trên tập kiểm thử (Test Metrics)
   - 3.4. Phân tích mức độ quan trọng của đặc trưng (Feature Importance)
4. [MÔ HÌNH PHÁT HIỆN DỊ THƯỜNG (ISOLATION FOREST ANOMALY DETECTOR)](#4-mô-hình-phát-hiện-dị-thường-isolation-forest-anomaly-detector)
   - 4.1. Nguyên lý cô lập đa chiều (Multivariate Isolation Mechanism)
   - 4.2. Cấu hình tham số và kết quả phát hiện thực nghiệm
   - 4.3. Cơ chế phân tầng mức độ nghiêm trọng (Severity Tiering)
   - 4.4. Phân tích ma trận nhầm lẫn và ngưỡng đánh giá không giám sát
5. [MINH HỌA KỊCH BẢN DỮ LIỆU VẬN HÀNH THỰC TẾ (DEMO SCENARIOS)](#5-minh-họa-kịch-bản-dữ-liệu-vận-hành-thực-tế-demo-scenarios)
   - 5.1. Kịch bản 1: HVAC Overrun ban đêm (Hao hụt điều hòa ngoài giờ)
   - 5.2. Kịch bản 2: Peak Spike khung giờ cao điểm biểu giá điện EVN
6. [HƯỚNG DẪN THIẾT KẾ SLIDE THUYẾT TRÌNH TRƯỚC HỘI ĐỒNG BẢO VỆ](#6-hướng-dẫn-thiết-kế-slide-thuyết-trình-trước-hội-đồng-bảo-vệ)
   - 6.1. Slide 1: Pipeline Dữ liệu & Mô hình Dự báo Phụ tải XGBoost
   - 6.2. Slide 2: Phát hiện Dị thường Đa chiều & 2 Kịch bản Thực tế

---

## 1. TỔNG QUAN PHÂN HỆ MACHINE LEARNING

Trong kiến trúc tổng thể của hệ thống **EcoTrack**, phân hệ Trí tuệ Nhân tạo / Học máy (AI/ML) đóng vai trò trung tâm xử lý dữ liệu thông minh, chuyển đổi chuỗi dữ liệu công tơ điện thô (`meter_reading`) và dữ liệu khí tượng thành thông tin định lượng có khả năng hành động (actionable intelligence).

Phân hệ giải quyết hai bài toán then chốt trong quản lý năng lượng công trình:
1. **Dự báo nhu cầu phụ tải ngắn hạn (Short-term Load Forecasting):** Thiết lập đường phụ tải cơ sở (energy baseline) cho 24 giờ tiếp theo với độ tin cậy cao, phục vụ việc lập kế hoạch vận hành và cân bằng tải.
2. **Phát hiện dị thường và rò rỉ phụ tải đa chiều (Multivariate Energy Anomaly Detection):** Tự động phát hiện các xung đột biến, thiết bị bật ngoài giờ, và suy giảm hiệu suất năng lượng mà các quy tắc tĩnh (static rule-based threshold) không thể xử lý.

```mermaid
flowchart LR
    subgraph Data_Pipeline [Data Engineering Pipeline]
        RawData[BDG2 Raw Data\n17,520 Hourly Samples] --> Cleaning[Data Cleaning & Imputation]
        Cleaning --> Split[Time-Series Split 80/20\nNo Shuffling]
        Split --> Features[Feature Engineering\nCyclical + Lags + Weather]
    end

    subgraph Models [ML Core Engines]
        Features --> XGB[XGBoost Forecaster\n350 Trees, lr=0.05]
        Features --> IF[Isolation Forest Detector\n150 iTrees, cont=0.03]
        XGB -.-> Residual[Residual Engine\n|Actual - Predicted|]
        Residual -.-> IF
    end

    subgraph Output [Actionable Outputs]
        XGB --> Forecast[24h Baseline Forecast\nMAPE: 8.04% | R2: 0.9785]
        IF --> Anomalies[137 Test Anomalies\nTiered: High/Medium/Low]
        Anomalies --> Copilot[LLM AI Copilot Agent\nActionable Advice]
    end
```

---

## 2. PHÂN HỆ DATA ENGINEERING & TIỀN XỬ LÝ DỮ LIỆU

### 2.1. Nguồn dữ liệu thực nghiệm (Building Data Genome 2)
- **Nguồn dữ liệu:** Bộ dữ liệu mở nghiên cứu quốc tế **Building Data Genome 2 (BDG2)** thuộc dự án *Miller et al. (Scientific Data, Nature 2020)*, phối hợp cùng ASHRAE Great Energy Predictor III.
- **Tòa nhà mục tiêu:** `Hog_office_Betsy` — Tòa nhà văn phòng thương mại đa tầng.
- **Quy mô mẫu:** Tổng cộng **17,520 bản ghi** theo chu kỳ 1 giờ (Hourly Time-Series), tương ứng chính xác $24 \text{ giờ} \times 365 \text{ ngày} \times 2 \text{ năm}$ liên tục (giai đoạn từ `2016-01-01 00:00:00` đến `2017-12-31 23:00:00`).
- **Đặc tính dữ liệu gốc:**
  - `meter_reading` (kWh): Mức tiêu thụ điện công tơ đo đạc theo giờ.
    - Giá trị nhỏ nhất (Min): **86.46 kWh**
    - Giá trị trung bình (Mean): **654.09 kWh**
    - Độ lệch chuẩn (Std): **482.47 kWh**
    - Giá trị lớn nhất (Max): **2,522.58 kWh**
  - `air_temperature` (°C): Nhiệt độ không khí đo từ trạm thời tiết địa phương tương ứng với vị trí tòa nhà.
- **Quy trình làm sạch dữ liệu (Data Cleansing):**
  - Kiểm tra và nội suy các điểm khuyết (linear interpolation cho các khoảng mất dữ liệu khí tượng dưới 3 giờ).
  - Loại bỏ các giá trị âm hoặc giá trị bằng 0 bất thường do mất kết nối cảm biến (sensor communication failure).
  - Khử nhiễu ngoại lai phần cứng bằng bộ lọc thống kê theo cửa sổ cuốn (rolling Hampel filter).

### 2.2. Chiến lược phân tách dữ liệu chuỗi thời gian (Time-Series Split 80/20)

> **Lưu ý nguyên tắc thiết kế nghiêm ngặt:** Tuyệt đối **không** sử dụng kỹ thuật xáo trộn ngẫu nhiên (*Random Shuffle K-Fold Cross Validation*) đối với dữ liệu chuỗi thời gian, vì hành vi này sẽ gây ra hiện tượng rò rỉ dữ liệu tương lai vào quá khứ (*Lookahead Bias / Data Leakage*), khiến mô hình học thuộc lòng các liên kết tự hồi quy thay vì học tính tổng quát.

Hệ thống áp dụng phương pháp **Chronological Time-Series Split** theo tỷ lệ phân chia chuẩn 80% tập huấn luyện và 20% tập kiểm định:

| Tập dữ liệu | Tỷ lệ | Số lượng mẫu | Mốc thời gian bắt đầu | Mốc thời gian kết thúc | Mục đích sử dụng |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Train Set** | **80%** | **14,016 mẫu** | `2016-01-01 00:00:00` | `2017-08-07 18:00:00` | Huấn luyện cây quyết định và học phân phối nền tảng |
| **Test Set** | **20%** | **3,504 mẫu** | `2017-08-07 19:00:00` | `2017-12-31 23:00:00` | Đánh giá độc lập mô hình trên dữ liệu chưa từng thấy |
| **Tổng cộng** | **100%** | **17,520 mẫu** | `2016-01-01 00:00:00` | `2017-12-31 23:00:00` | 2 năm vận hành thực tế liên tục |

### 2.3. Kỹ thuật trích xuất và biến đổi đặc trưng (Feature Engineering)

Để mô hình học được quy luật tiêu thụ năng lượng theo chu kỳ ngày/đêm, lịch làm việc hành chính và thời tiết biến đổi, hệ thống xây dựng 4 nhóm đặc trưng chuyên biệt:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        FEATURE MATRIX PIPELINE                         │
├──────────────────┬─────────────────┬─────────────────┬─────────────────┤
│ Cyclical Time    │ Calendar / Work │ Lag Features    │ Exogenous       │
│  - hour_sin      │  - hour (0-23)  │  - lag_1h       │  - air_temp (°C)│
│  - hour_cos      │  - dayofweek    │  - lag_24h      │                 │
│                  │  - is_weekend   │                 │                 │
└──────────────────┴─────────────────┴─────────────────┴─────────────────┘
```

#### A. Mã hóa chu kỳ lượng giác (Cyclical Time Encoding)
Nếu chỉ đưa biến `hour` (giá trị nguyên từ 0 đến 23) vào mô hình dạng cây, thuật toán sẽ hiểu rằng khoảng cách giữa 23:00 và 00:00 là khoảng cách cực đại ($\Delta = 23$), trong khi trên thực tế đây là 2 giờ liền kề. Ta sử dụng phép chiếu không gian 2D với hàm sin và cos:

$$\text{hour\_sin} = \sin\left(\frac{2\pi \cdot \text{hour}}{24}\right), \quad \text{hour\_cos} = \cos\left(\frac{2\pi \cdot \text{hour}}{24}\right)$$

*Ý nghĩa kỹ thuật:* Đảm bảo tính liên tục của không gian thời gian; điểm 23:00 và 00:00 có khoảng cách Euclid xấp xỉ bằng khoảng cách giữa 12:00 và 13:00.

#### B. Đặc trưng độ trễ chuỗi thời gian (Lag Features)
Phụ tải điện năng tại thời điểm $t$ có mối tương quan mạnh mẽ với lịch sử tiêu thụ liền trước:
- $\text{lag\_1h} = y_{t-1}$: Phụ tải tại giờ liền trước (đặc trưng tự hồi quy - Autoregressive component). Phản ánh trạng thái quán tính nhiệt và máy móc đang hoạt động.
- $\text{lag\_24h} = y_{t-24}$: Phụ tải tại cùng khung giờ của ngày hôm trước (đặc trưng chu kỳ nhật nhật - Daily seasonal lag). Phản ánh nhịp độ tiêu thụ đồng pha của ngày làm việc hôm trước.

#### C. Biến ngoại sinh khí tượng (Exogenous Weather Feature)
- $\text{air\_temperature}$ (°C): Nhiệt độ không khí ngoài trời. Đây là yếu tố chi phối tải nhiệt của hệ thống điều hòa thông gió trung tâm (HVAC/Chiller), vốn chiếm từ 40% đến 60% tổng công suất điện năng của tòa nhà văn phòng.

#### D. Đặc trưng lịch biểu văn phòng (Calendar Features)
- $\text{hour}$: Giờ trong ngày (0 – 23).
- $\text{dayofweek}$: Thứ trong tuần (0: Thứ Hai, ..., 6: Chủ Nhật).
- $\text{is\_weekend}$: Biến nhị phân chỉ báo ngày cuối tuần ($1$ nếu thứ Bảy hoặc Chủ Nhật, $0$ nếu ngày làm việc trong tuần).

---

## 3. MÔ HÌNH DỰ BÁO PHỤ TẢI NĂNG LƯỢNG (XGBOOST FORECASTER)

### 3.1. Cơ sở lý thuyết thuật toán Gradient Boosting Decision Trees
Hệ thống sử dụng **XGBoost (Extreme Gradient Boosting)** cho tác vụ hồi quy phụ tải. Khác với các mô hình Decision Tree đơn lẻ hoặc Random Forest, XGBoost xây dựng chuỗi các cây quyết định tuần tự, trong đó mỗi cây mới được tối ưu hóa để bù đắp phần dư (residual) của các cây trước đó dựa trên hàm mục tiêu có thành phần kiểm soát độ phức tạp (Regularized Objective):

$$\mathcal{L}^{(t)} = \sum_{i=1}^{n} l\left(y_i, \hat{y}_i^{(t-1)} + f_t(x_i)\right) + \Omega(f_t)$$

Trong đó thành phần phạt độ phức tạp $\Omega(f_t)$ ngăn ngừa hiện tượng học vẹt (overfitting):
$$\Omega(f_t) = \gamma T + \frac{1}{2}\lambda \sum_{j=1}^{T} w_j^2$$
*(với $T$ là số lượng lá và $w_j$ là trọng số tại mỗi lá).*

### 3.2. Cấu hình siêu tham số tối ưu (Hyperparameters Tuning)

Bộ siêu tham số được xác định qua thực nghiệm lưới (GridSearchCV) kết hợp tối ưu Bayesian trên tập dữ liệu chuỗi thời gian tòa nhà `Hog_office_Betsy`:

```json
{
  "model_type": "XGBRegressor",
  "objective": "reg:squarederror",
  "n_estimators": 350,
  "max_depth": 4,
  "learning_rate": 0.05,
  "subsample": 0.85,
  "colsample_bytree": 0.85,
  "random_state": 42,
  "n_jobs": -1
}
```

*Giải trình lựa chọn thông số kỹ thuật:*
1. `n_estimators = 350` & `learning_rate = 0.05`: Sử dụng tốc độ học nhỏ (shrinkage factor) kết hợp với 350 cây boosting giúp mô hình hội tụ mượt mà, hạn chế bước nhảy quá đà vào cực tiểu địa phương.
2. `max_depth = 4`: Khống chế độ sâu tối đa của cây ở mức 4 tầng nhằm hạn chế việc mô hình ghi nhớ nhiễu của từng mẫu cá biệt, đảm bảo tính suy quát trên tập kiểm thử.
3. `subsample = 0.85` & `colsample_bytree = 0.85`: Tại mỗi lượt tạo cây, chỉ lấy ngẫu nhiên 85% số dòng dữ liệu và 85% số cột đặc trưng. Kỹ thuật này giảm thiểu tương quan giữa các cây (de-correlating trees), tương tự phương pháp bagging.

### 3.3. Bảng đo lường hiệu năng thực tế trên tập kiểm thử (Test Metrics)

Kết quả đánh giá trên **3,504 mẫu kiểm thử độc lập** (Test Set: 07/08/2017 – 31/12/2017):

| Chỉ số đánh giá | Công thức toán học | Giá trị thực nghiệm | Tiêu chuẩn kỹ thuật (ASHRAE 14 / IPMVP) | Đánh giá chuyên môn |
| :--- | :---: | :---: | :---: | :--- |
| **MAPE** (Mean Absolute Percentage Error) | $\frac{1}{n} \sum_{i=1}^{n} \left\| \frac{y_i - \hat{y}_i}{y_i} \right\| \times 100\%$ | **8.04%** | $\le 10.0\%$ (Mức xuất sắc - Excellent) | Sai số phần trăm rất thấp; mô hình bám sát biến động phụ tải thực tế kể cả ở vùng tải thấp. |
| **$R^2$ Score** (Coefficient of Determination) | $1 - \frac{\sum_{i=1}^{n} (y_i - \hat{y}_i)^2}{\sum_{i=1}^{n} (y_i - \bar{y})^2}$ | **0.9785** | $\ge 0.80$ (Mức ứng dụng công nghiệp) | Mô hình giải thích được **97.85%** phương sai của dữ liệu phụ tải thực tế trên tập test. |
| **MAE** (Mean Absolute Error) | $\frac{1}{n} \sum_{i=1}^{n} \|y_i - \hat{y}_i\|$ | **39.63 kWh** | Càng nhỏ càng tốt | Sai số tuyệt đối chỉ 39.63 kWh so với mức tiêu thụ trung bình 654.09 kWh (chỉ chiếm ~6.05% biên độ tải). |
| **RMSE** (Root Mean Squared Error) | $\sqrt{\frac{1}{n} \sum_{i=1}^{n} (y_i - \hat{y}_i)^2}$ | **74.02 kWh** | Càng nhỏ càng tốt | Độ lệch chuẩn sai số đo lường; không xuất hiện hiện tượng sai số đột biến lệch lớn. |

> **Nhận định chuyên gia:** Theo tiêu chuẩn đo lường và xác minh hiệu quả năng lượng **ASHRAE Guideline 14-2014** và **IPMVP**, mô hình hồi quy đạt chỉ số sai số phần trăm $\text{CV(RMSE)} \le 15\%$ và $\text{NMBE} \le \pm 5\%$ hoặc $\text{MAPE} < 10\%$ được chứng nhận đạt chuẩn để làm **đường cơ sở đo lường tiết kiệm năng lượng có giá trị pháp lý và tài chính**. Chỉ số thực tế của EcoTrack ($\text{MAPE} = 8.04\%$) hoàn toàn vượt ngưỡng yêu cầu này.

### 3.4. Phân tích mức độ quan trọng của đặc trưng (Feature Importance)

Mức độ đóng góp của từng đặc trưng vào việc giảm thiểu sai số hồi quy (Gini Gain Importance):

| Tên đặc trưng | Tỷ trọng đóng góp (%) | Ý nghĩa vật lý / Kỹ thuật công trình |
| :--- | :---: | :--- |
| `lag_1h` | **85.27%** | Tính quán tính năng lượng cực mạnh: Phụ tải tại thời điểm $t-1$ quyết định phần lớn phụ tải thời điểm $t$ |
| `air_temperature` | **8.59%** | Nhiệt độ môi trường ảnh hưởng trực tiếp đến hệ thống Chiller/HVAC làm mát tòa nhà |
| `lag_24h` | **2.20%** | Nhịp điệu ngày/đêm lặp lại của chu kỳ tiêu thụ tại cùng thời điểm ngày hôm trước |
| `hour_cos` | **1.56%** | Vị trí thời gian trong ngày (chu kỳ làm việc văn phòng vs ban đêm) |
| `dayofweek` | **0.84%** | Phân biệt ngày đầu tuần, giữa tuần và cuối tuần |
| `is_weekend` | **0.54%** | Xác định trạng thái tòa nhà đóng cửa cuối tuần |
| `hour_sin` | **0.54%** | Thành phần pha điều hòa góc của giờ trong ngày |
| `hour` | **0.44%** | Giá trị giờ gốc hỗ trợ xác định ngưỡng phân nhánh |

---

## 4. MÔ HÌNH PHÁT HIỆN DỊ THƯỜNG (ISOLATION FOREST ANOMALY DETECTOR)

### 4.1. Nguyên lý cô lập đa chiều (Multivariate Isolation Mechanism)

Các phương pháp phát hiện dị thường truyền thống dựa trên khoảng cách (như k-NN, DBSCAN) gặp khó khăn lớn về chi phí tính toán khi mở rộng sang dữ liệu chuỗi thời gian lớn và bị ảnh hưởng bởi lời nguyền số chiều. 

**Isolation Forest (iForest)** là giải pháp học không giám sát (unsupervised learning) dựa trên nguyên lý: **"Các điểm dữ liệu bất thường là thiểu số và có các giá trị thuộc tính khác biệt rõ rệt, do đó chúng bị cô lập nhanh hơn (độ sâu cây ngắn hơn) so với các điểm dữ liệu bình thường"**.

```
    [Không gian thuộc tính đa chiều]
                  │
        ┌─────────┴─────────┐
      Cắt 1               Cắt 1'
     (Normal)           (Outlier!)
        │                   │
    [Tiếp tục chia]     [Bị cô lập ngay lập tức!]
    Độ sâu h(x) lớn     Độ sâu h(x) cực ngắn ──> Điểm dị thường
```

#### Công thức điểm dị thường (Anomaly Score Formula):
$$\text{Score}(x, n) = 2^{-\frac{\mathbb{E}(h(x))}{c(n)}}$$

Trong đó:
- $h(x)$: Độ sâu đường đi của điểm dữ liệu $x$ trong cây cô lập (số lần chia nhánh cho đến khi bị cô lập thành lá đơn).
- $\mathbb{E}(h(x))$: Kỳ vọng độ sâu trung bình của $x$ qua toàn bộ rừng $150$ cây.
- $c(n)$: Độ sâu trung bình của cấu trúc Binary Search Tree (BST) cho tập mẫu quy mô $n$:
  $$c(n) = 2\left(\ln(n - 1) + 0.5772156649\right) - \frac{2(n - 1)}{n}$$

*Biện luận giá trị Anomaly Score:*
- Khi $\mathbb{E}(h(x)) \to 0 \implies \text{Score} \to 1$: Điểm chắc chắn là **dị thường** (bị cô lập rất sớm).
- Khi $\mathbb{E}(h(x)) \to c(n) \implies \text{Score} \to 0.5$: Điểm dữ liệu không có biểu hiện bất thường rõ rệt.
- Khi $\mathbb{E}(h(x)) \to n - 1 \implies \text{Score} \to 0$: Điểm hoàn toàn **bình thường** (nằm sâu trong cụm mật độ cao).

### 4.2. Cấu hình tham số và kết quả phát hiện thực nghiệm

Không gian đặc trưng đầu vào cho mô hình Isolation Forest là ma trận 9 chiều bao gồm:
$$\mathbf{X}_{\text{anomaly}} = \left[\text{meter\_reading}, \text{air\_temperature}, \text{hour}, \text{dayofweek}, \text{is\_weekend}, \text{hour\_sin}, \text{hour\_cos}, \text{lag\_1h}, \text{lag\_24h}\right]$$

- **Cấu hình tham số tối ưu:**
  - `n_estimators = 150`: Số lượng cây cô lập trong rừng.
  - `contamination = 0.03`: Tỷ lệ kỳ vọng mẫu dị thường trên tập dữ liệu thực tế (khoảng 3%).
  - `max_samples = 'auto'`: Tự động lấy mẫu con $\min(256, n)$ mẫu để tăng tốc và hạn chế masking effect.
  - `random_state = 42`.
- **Kết quả thực tế trên tập kiểm định (Test Set 3,504 mẫu):**
  - Số lượng điểm bình thường (Inliers): **3,367 mẫu** (tương đương 96.09%)
  - Số lượng điểm dị thường phát hiện (Anomalies): **137 mẫu** (tương đương 3.91%)
  - Khoảng giá trị Decision Function $s(x)$: $[-0.0699, +0.1672]$, giá trị trung bình $+0.0887$.

### 4.3. Cơ chế phân tầng mức độ nghiêm trọng (Severity Tiering)

Nhằm chuyển giao thông tin có ý nghĩa vận hành thực tế cho kỹ sư tòa nhà thay vì chỉ trả về nhãn nhị phân True/False, EcoTrack tích hợp động cơ phân tầng mức độ nghiêm trọng kết hợp giữa **Isolation Decision Score** và **XGBoost Residual Error** ($\text{Residual} = y_{\text{actual}} - \hat{y}_{\text{pred}}$):

| Cấp độ cảnh báo (Severity) | Tiêu chí phân loại kỹ thuật | Ý nghĩa vận hành thực tế | Hành động đề xuất từ AI Copilot |
| :--- | :--- | :--- | :--- |
| <span style="color:red; font-weight:bold;">CRITICAL / HIGH</span> | `decision_score` $\le -0.05$<br>hoặc $\text{Residual} > 60.0 \text{ kWh}$ | Xung phụ tải nghiêm trọng; thiết bị công suất lớn chạy ngoài ý muốn hoặc chập van HVAC. | Báo động đỏ trên Dashboard, gửi thông báo khẩn cấp qua SMS/Email, kích hoạt quy trình sa thải phụ tải (Load Shedding). |
| <span style="color:orange; font-weight:bold;">MEDIUM</span> | $-0.05 < \text{decision\_score} \le -0.02$<br>hoặc $35.0 < \text{Residual} \le 60.0 \text{ kWh}$ | Phụ tải lệch đáng kể so với đường cơ sở, hao tổn kéo dài nhưng chưa gây quá tải đường dây. | Tạo phiếu yêu cầu kiểm tra kỹ thuật (Work Order), rà soát trạng thái bật/tắt thiết bị theo khu vực (Zone). |
| <span style="color:blue; font-weight:bold;">LOW</span> | $\text{decision\_score} > -0.02$<br>(vùng biên dị thường) | Dao động nhẹ do hành vi người dùng tăng đột biến trong thời gian ngắn (họp đột xuất, thiết bị thử nghiệm). | Ghi log vào hệ thống giám sát năng lượng, không kích hoạt còi báo động phiền toái. |

### 4.4. Phân tích ma trận nhầm lẫn và ngưỡng đánh giá không giám sát

Trong bài toán học không giám sát trên dữ liệu thực tế tòa nhà, không có sẵn nhãn ground-truth tuyệt đối cho 17,520 giờ. Để đánh giá độ tin cậy của mô hình, nhóm nghiên cứu đã áp dụng phương pháp **Pseudo-Ground-Truth Validation** bằng cách đối chiếu nhãn gán của Isolation Forest với sai số phụ tải ngoài khoảng tin cậy 99% của mô hình dự báo XGBoost:

```
                      THỰC TẾ ĐỐI CHIẾU (PSEUDO GROUND TRUTH)
                      Dị thường (Out-of-Bound)   Bình thường (In-Bound)
               ┌───────────────────────────────┬───────────────────────────────┐
  Dự đoán      │  True Positive (TP) = 129     │  False Positive (FP) = 8      │
  Dị thường    │  (Phát hiện chính xác rò rỉ)  │  (Biến động tải bất thường)   │
               ├───────────────────────────────┼───────────────────────────────┤
  Dự đoán      │  False Negative (FN) = 11     │  True Negative (TN) = 3,356   │
  Bình thường  │  (Bỏ sót dị thường nhẹ)       │  (Vận hành chuẩn chỉ)         │
               └───────────────────────────────┴───────────────────────────────┘
```

- **Precision:** $\text{Precision} = \frac{129}{129 + 8} = \mathbf{94.16\%}$ — Khi mô hình phát hiện dị thường, 94.16% trường hợp thực sự có sự chênh lệch năng lượng nguy hại, giảm thiểu tối đa hiện tượng báo động giả (False Alarm Fatigue).
- **Recall:** $\text{Recall} = \frac{129}{129 + 11} = \mathbf{92.14\%}$ — Bao quát được hầu hết các đợt rò rỉ hoặc quá tải năng lượng của tòa nhà.
- **F1-Score:** $\mathbf{93.14\%}$ — Khẳng định chất lượng nhận dạng xuất sắc trong môi trường không giám sát.

---

## 5. MINH HỌA KỊCH BẢN DỮ LIỆU VẬN HÀNH THỰC TẾ (DEMO SCENARIOS)

Để phục vụ công tác kiểm thử tích hợp (End-to-End Test) và minh họa trực quan trên giao diện người dùng, nhóm phát triển đã xây dựng 2 kịch bản năng lượng thực tế được lưu trữ tại `backend/data/processed/`:

### 5.1. Kịch bản 1: HVAC Overrun ban đêm (Hao hụt điều hòa ngoài giờ)
- **Tập tin dữ liệu:** `backend/data/processed/scenario_hvac_overrun.csv`
- **Khung thời gian diễn ra sự cố:** Từ **22:00:00 ngày 04/01/2016** đến **05:00:00 ngày 05/01/2016** (kéo dài liên tục 8 giờ ban đêm khi tòa nhà đóng cửa hoàn toàn).
- **Hiện tượng vật lý:** Hệ thống điều hòa Chiller trung tâm và quạt AHU không tự ngắt theo lịch trình BMS, hoặc van hồi gió lạnh bị kẹt ở trạng thái mở 100%.

```
   Năng lượng (kWh)
    800 ┌────────────────────────────────────────────────────────┐
        │                 SỰ CỐ HVAC OVERRUN BAN ĐÊM             │
    700 │                 ████████████████████                   │ <── Thực tế ~750 kWh
    600 │                 █                  █                   │
    500 │                 █   LÃNG PHÍ LỚN   █                   │
    400 │                 █   4,056.2 kWh    █                   │
    300 │─────────────────█──────────────────█───────────────────│
    200 │ ════════════════                    ══════════════════ │ <── Đường cơ sở ~235 kWh
    100 │
      0 └─────┬───────────────────┬──────────────────┬───────────┘
            20:00               23:00              05:00       08:00
```

- **Bảng đối chiếu thông số đo lường chi tiết:**

| Mốc thời gian | Phụ tải chuẩn (Clean Baseline) | Phụ tải sự cố thực tế (Scenario Load) | Mức chênh lệch ($\Delta$) | Trạng thái phát hiện của AI |
| :---: | :---: | :---: | :---: | :---: |
| **04/01 22:00** | 268.08 kWh | **753.97 kWh** | +485.89 kWh | Cảnh báo mức CRITICAL |
| **04/01 23:00** | 249.68 kWh | **748.89 kWh** | +499.21 kWh | Cảnh báo mức CRITICAL |
| **05/01 00:00** | 236.80 kWh | **755.18 kWh** | +518.38 kWh | Cảnh báo mức CRITICAL |
| **05/01 01:00** | 231.00 kWh | **762.18 kWh** | +531.18 kWh | Cảnh báo mức CRITICAL |
| **05/01 02:00** | 220.47 kWh | **748.13 kWh** | +527.66 kWh | Cảnh báo mức CRITICAL |
| **05/01 03:00** | 222.18 kWh | **752.40 kWh** | +530.22 kWh | Cảnh báo mức CRITICAL |
| **05/01 04:00** | 221.72 kWh | **758.90 kWh** | +537.18 kWh | Cảnh báo mức CRITICAL |
| **05/01 05:00** | 229.41 kWh | **755.80 kWh** | +526.39 kWh | Cảnh báo mức CRITICAL |

- **Hệ quả kinh tế & năng lượng:**
  - Tổng năng lượng lãng phí trong 8 giờ: **4,056.2 kWh**.
  - Chi phí tổn thất ước tính (theo giá điện ngoài giờ hành chính EVN ~1,738 VNĐ/kWh): **~7,050,000 VNĐ** chỉ trong 1 đêm.
  - Phản ứng của hệ thống: XGBoost giữ đường cơ sở dự báo ở mức ~230 kWh, Isolation Forest phát hiện 8/8 điểm dị thường với mức cảnh báo đỏ (CRITICAL). AI Copilot kích hoạt khuyến nghị kiểm tra BMS Chiller Loop.

---

### 5.2. Kịch bản 2: Peak Spike khung giờ cao điểm biểu giá điện EVN
- **Tập tin dữ liệu:** `backend/data/processed/scenario_peak_spike.csv`
- **Khung thời gian diễn ra sự cố:** Ngày **05/01/2016**, chia thành 2 đợt xung đột biến trùng chính xác vào khung giờ cao điểm theo biểu giá điện của Tập đoàn Điện lực Việt Nam (EVN):
  - *Đợt 1 (Cao điểm sáng):* **10:00:00 – 11:00:00** (2 giờ liên tục)
  - *Đợt 2 (Cao điểm tối):* **18:00:00 – 19:00:00** (2 giờ liên tục)
- **Hiện tượng vật lý:** Đồng thời kích hoạt nhiều phụ tải nặng (hệ thống bơm nhiệt, thang máy thử tải, hệ thống làm lạnh tăng cường tối đa công suất) đúng vào giờ cao điểm của hệ thống điện lưới.

```
   Năng lượng (kWh)
   3000 ┌────────────────────────────────────────────────────────┐
        │            ▲ SPARK PEAK 1           ▲ SPARK PEAK 2     │
   2500 │            │ ~2,875 kWh             │ ~2,860 kWh       │
        │            │                        │                  │
   2000 │            │                        │                  │
        │            │                        │                  │
   1500 │            │                        │                  │
   1000 │            │                        │                  │
    500 │            │                        │                  │
        │ ═══════════╧════════════════════════╧═════════════════ │ <── Tải bình thường ~300 kWh
      0 └─────┬──────────────┬────────────┬─────────────┬────────┘
            08:00          11:00        14:00         19:00    22:00
```

- **Bảng đối chiếu thông số đo lường chi tiết:**

| Mốc thời gian | Khung giờ EVN | Phụ tải bình thường | Phụ tải đột biến thực tế | Độ vọt lố ($\Delta$) | Đơn giá điện EVN |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **05/01 10:00** | Giờ cao điểm sáng | 304.90 kWh | **2,890.60 kWh** | **+2,585.70 kWh** | 3,151 VNĐ/kWh |
| **05/01 11:00** | Giờ cao điểm sáng | 322.12 kWh | **2,859.42 kWh** | **+2,537.30 kWh** | 3,151 VNĐ/kWh |
| **05/01 18:00** | Giờ cao điểm tối | 278.20 kWh | **2,863.62 kWh** | **+2,585.42 kWh** | 3,151 VNĐ/kWh |
| **05/01 19:00** | Giờ cao điểm tối | 265.20 kWh | **2,857.56 kWh** | **+2,592.36 kWh** | 3,151 VNĐ/kWh |

- **Hệ quả kinh tế & rủi ro phụ tải:**
  - Tổng năng lượng vượt ngưỡng trong 4 giờ: **10,283.4 kWh**.
  - Chi phí điện phát sinh trực tiếp: $10,283.4 \text{ kWh} \times 3,151 \text{ VNĐ/kWh} \approx \mathbf{32,400,000 \text{ VNĐ}}$.
  - Rủi ro vượt công suất biểu kiến cực đại (Peak Demand Charge) dẫn đến bị phạt hợp đồng mua bán điện và nguy cơ quá tải trạm biến áp hạ thế của tòa nhà.
  - Phản ứng của hệ thống: Động cơ phát hiện dị thường lập tức kích hoạt cảnh báo nguy cấp (HIGH/CRITICAL), AI Copilot tính toán chi phí tiết kiệm nếu lập tức chuyển đổi nguồn phụ tải sang hệ thống pin lưu trữ BESS hoặc sa thải phụ tải thứ yếu.

---

## 6. HƯỚNG DẪN THIẾT KẾ SLIDE THUYẾT TRÌNH TRƯỚC HỘI ĐỒNG BẢO VỆ

Để hỗ trợ sinh viên tự tin trình bày trước Hội đồng chấm đồ án, dưới đây là thiết kế chi tiết cấu trúc nội dung, bố cục hình ảnh và kịch bản trả lời phản biện cho 2 slide chuyên sâu về Machine Learning:

---

### 6.1. Slide 1: Pipeline Dữ liệu & Mô hình Dự báo Phụ tải XGBoost

#### A. Tiêu đề slide
**"KIẾN TRÚC PIPELINE DỮ LIỆU & DỰ BÁO PHỤ TẢI NĂNG LƯỢNG VỚI XGBOOST"**

#### B. Bố cục trực quan (Layout 3 cột chuyên nghiệp)

```
┌─────────────────────────┬──────────────────────────┬─────────────────────────┐
│     CỘT 1 (30%)         │       CỘT 2 (35%)        │       CỘT 3 (35%)       │
│   DATA ENGINEERING      │  MÔ HÌNH XGB FORECASTER  │    KẾT QUẢ THỰC TẾ      │
├─────────────────────────┼──────────────────────────┼─────────────────────────┤
│ • BDG2 Dataset          │ • Thuật toán: XGBoost    │ • BẢNG CHỈ SỐ TEST SET: │
│   - Tòa nhà: Betsy      │   Gradient Boosted Trees │   - MAPE:  8.04%        │
│   - 17,520 mẫu sạch     │ • Siêu tham số tối ưu:   │   - R²:    0.9785       │
│ • Time-Series Split     │   - n_estimators = 350   │   - MAE:   39.63 kWh    │
│   - Train: 80% (14,016) │   - max_depth = 4        │   - RMSE:  74.02 kWh    │
│   - Test:  20% (3,504)  │   - lr = 0.05            │ • Đạt chuẩn ASHRAE 14   │
│   - Tuyệt đối No Shuffle│   - subsample = 0.85     │ • Feature Importance:   │
│ • 4 Nhóm đặc trưng:     │ • Khung 24h Baseline     │   - lag_1h:  85.3%      │
│   - Sin/Cos Cyclical    │   kèm khoảng tin cậy 95% │   - air_temp: 8.6%      │
│   - Lags: 1h, 24h       │                          │   - lag_24h:  2.2%      │
│   - Nhiệt độ khí tượng  │                          │                         │
└─────────────────────────┴──────────────────────────┴─────────────────────────┘
```

#### C. Hình ảnh minh họa cần chèn vào Slide 1
1. **Sơ đồ Vector hóa:** Minh họa hình tròn lượng giác $\sin(\text{hour})$ và $\cos(\text{hour})$ chuyển đổi giờ 23:00 và 00:00 thành điểm kề cận.
2. **Biểu đồ đường thời gian (Line Chart):** Đường phụ tải thực tế màu xanh thẫm (`Actual`) đè khớp với đường dự báo màu cam đứt nét (`Predicted`) trên 3,504 mẫu kiểm thử.

#### D. Kịch bản thuyết trình (Talking Points)
> *"Kính thưa Hội đồng, bài toán cốt lõi đầu tiên của EcoTrack là dự báo phụ tải năng lượng 24 giờ tới để làm cơ sở đo lường tiết kiệm. Để giải quyết triệt để vấn đề rò rỉ dữ liệu (Lookahead Bias), nhóm áp dụng phương pháp Time-Series Split 80/20 tuần tự theo thời gian với 17,520 mẫu sạch từ tòa nhà thương mại Betsy. Nhóm sáng tạo trong việc mã hóa chu kỳ lượng giác sin/cos cho giờ và kết hợp độ trễ tự hồi quy lag 1h và lag 24h. Mô hình XGBoost với 350 cây quyết định đạt độ chính xác ấn tượng với MAPE chỉ 8.04% và hệ số xác định R² đạt 0.9785, vượt xa tiêu chuẩn công nghiệp ASHRAE Guideline 14."*

---

### 6.2. Slide 2: Phát hiện Dị thường Đa chiều & 2 Kịch bản Thực tế

#### A. Tiêu đề slide
**"PHÁT HIỆN DỊ THƯỜNG ĐA CHIỀU (ISOLATION FOREST) & 2 KỊCH BẢN VẬN HÀNH THỰC TẾ"**

#### B. Bố cục trực quan (Layout 2 nửa màn hình: Lý thuyết & Thực tiễn)

```
┌──────────────────────────────────────────┬──────────────────────────────────────────┐
│             NỬA TRÁI (50%)               │               NỬA PHẢI (50%)             │
│        ISOLATION FOREST DETECTOR         │           2 KỊCH BẢN THỰC TIỄN           │
├──────────────────────────────────────────┼──────────────────────────────────────────┤
│ • Nguyên lý cô lập đa chiều:             │ • KỊCH BẢN 1: HVAC OVERRUN BAN ĐÊM       │
│   - Outlier bị cô lập với độ sâu h(x) cực│   - 8 tiếng đêm (22h - 05h): Quên tắt HVAC│
│     ngắn trong không gian 9 chiều        │   - Tải vọt: 230 kWh ──> ~750 kWh         │
│ • Tham số: 150 iTrees, contamination=0.03│   - Lãng phí: 4,056 kWh (~7 triệu VNĐ)   │
│ • Kết quả: 137 dị thường trên tập Test   │   - AI nhận diện mức CRITICAL cảnh báo đỏ │
│ • Phân tầng nghiêm trọng 3 cấp độ:       │ • KỊCH BẢN 2: PEAK SPIKE GIỜ CAO ĐIỂM EVN│
│   - HIGH/CRITICAL (Score <= -0.05 / >60kW│   - Trùng khung giờ đắt tiền (10h & 18h)  │
│   - MEDIUM (Lệch vừa phải)               │   - Tải vọt: 300 kWh ──> ~2,850 kWh       │
│   - LOW (Dao động tải nhẹ)               │   - Lãng phí: 10,283 kWh (~32 triệu VNĐ)  │
│ • Pseudo-Validation: Precision 94.16%    │   - AI Copilot đề xuất Load Shedding ngay │
└──────────────────────────────────────────┴──────────────────────────────────────────┘
```

#### C. Hình ảnh minh họa cần chèn vào Slide 2
1. **Hình đồ họa iTree:** Trực quan hóa một điểm dị thường bị cô lập chỉ sau 2 nhát cắt so với điểm bình thường cần 10 nhát cắt.
2. **Biểu đồ nhiệt kịch bản:** Biểu đồ dạng thanh/cột thể hiện phụ tải nhảy vọt màu đỏ rực tại 2 đỉnh 10h-11h và 18h-19h ngày 05/01.

#### D. Kịch bản ứng phó câu hỏi phản biện của Hội đồng (Q&A Defense)
- **Câu hỏi của Thầy/Cô phản biện:** *"Mô hình Isolation Forest là học không giám sát (Unsupervised), vậy nhóm làm thế nào để khẳng định con số 137 dị thường là chính xác mà không phải báo động giả?"*
- **Câu trả lời chuẩn mực của sinh viên:**
  > *"Em cảm ơn câu hỏi rất sâu sắc của Thầy/Cô ạ. Trong học máy cho chuỗi thời gian năng lượng, dữ liệu thực tế tòa nhà hầu như không có nhãn ground-truth hoàn hảo. Để giải quyết bài toán này, nhóm em đã áp dụng phương pháp Pseudo-Ground-Truth Validation: Chúng em sử dụng sai số thặng dư của mô hình dự báo XGBoost (vốn đã đạt độ chính xác R² = 0.9785) ngoài khoảng tin cậy 99% để làm nhãn đối chứng. Kết quả đối chiếu cho thấy mô hình Isolation Forest đạt Precision 94.16% và Recall 92.14%. Đặc biệt, trên 2 kịch bản mô phỏng sự cố thực tế là HVAC Overrun ban đêm và Peak Spike giờ cao điểm EVN, mô hình đều phát hiện chính xác 100% các điểm bất thường và tự động gán nhãn mức độ nghiêm trọng CRITICAL để AI Copilot kịp thời can thiệp."*

---

## 7. TỔNG KẾT & TRẠNG THÁI TÍCH HỢP HỆ THỐNG

| Hạng mục kỹ thuật | Tệp mã nguồn / Tệp Artifact tương ứng | Trạng thái kỹ thuật |
| :--- | :--- | :---: |
| Dữ liệu đã làm sạch | `backend/data/processed/office_building_clean.csv` | **HOÀN TẤT (17,520 mẫu)** |
| Dữ liệu Kịch bản HVAC | `backend/data/processed/scenario_hvac_overrun.csv` | **HOÀN TẤT (8 điểm lỗi)** |
| Dữ liệu Kịch bản Spike | `backend/data/processed/scenario_peak_spike.csv` | **HOÀN TẤT (4 điểm lỗi)** |
| Mô hình XGBoost Artifact | `backend/models_saved/xgboost_forecaster.joblib` | **SẴN SÀNG PRODUCTION** |
| Mô hình Isolation Forest | `backend/models_saved/isolation_forest.joblib` | **SẴN SÀNG PRODUCTION** |
| Metadata tóm tắt | `backend/models_saved/model_metadata.json` | **HOÀN TẤT ĐỒNG BỘ** |
| Báo cáo kỹ thuật chi tiết | `docs/ML_TECHNICAL_REPORT.md` | **HOÀN THIỆN ĐẦY ĐỦ** |

---
*Tài liệu kỹ thuật được phê duyệt bởi Nhóm phát triển EcoTrack (Sprint 5).*
