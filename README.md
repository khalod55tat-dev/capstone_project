
[README.md](https://github.com/user-attachments/files/26620126/README.md)
# 🌊 Solar-Powered IoT Water Quality Monitoring and Advisory System

> **🏆 Winner — Best Theme Project (Communication Theme Award) | EECS2026 Capstone Showcase, UTM**
![WhatsApp Image 2026-04-10 at 12 51 58 PM](https://github.com/user-attachments/assets/9b332de8-badf-480e-99e5-c62cda85a4fd)

A portable, energy-independent water quality monitoring system built for off-grid and rural communities. The system combines solar power, multi-stage water purification, UV sterilization, and real-time IoT monitoring via an ESP32 microcontroller — all accessible through a web dashboard and mobile app.


---

## 📌 Project Overview

Rural communities and outdoor enthusiasts often lack access to real-time water quality information. Existing solutions are either too expensive, not portable, or don't provide verified safety data. This system solves that by delivering:

- **Real-time monitoring** of pH, Turbidity (NTU), and TDS (mg/L)
- **Multi-stage purification** — sediment filtration + UV sterilization
- **Solar-powered operation** with battery backup for off-grid use
- **IoT web dashboard** with Water Quality Index (WQI), analysis reports, and email alerts
- **Mobile app** via Blynk for instant notifications

---

## 🏗️ System Architecture

The system has three integrated subsystems:

```
Solar Panel → Charge Controller → Battery → Solar Inverter → UV Sterilizer
                                                    ↓
Raw Water → Multistage Filter → UV Sterilizer → Purified Storage Tank
                                                    ↓
                              ESP32 ← pH / Turbidity / TDS Sensors
                                ↓
                    Wi-Fi → Blynk Server + ThingSpeak
                                ↓
                        Web Dashboard (Flask App)
```

---

## ⚙️ Hardware Components

| Component | Purpose |
|-----------|---------|
| ESP32 Microcontroller | Central processor, Wi-Fi, sensor reading |
| pH Sensor (Pin 34) | Measures water acidity/alkalinity |
| Turbidity Sensor (Pin 33) | Measures water clarity in NTU |
| TDS Sensor (Pin 35) | Measures dissolved solids in mg/L |
| 18V Solar Panel | Renewable energy source |
| 10A Charge Controller | Battery charge regulation |
| 12Ah Lead-Acid Battery | Energy storage & backup |
| 220W Solar Inverter | DC to AC for UV sterilizer |
| Multistage Water Filter | Physical filtration (sediment, carbon, UF) |
| UV Light Sterilizer | Biological disinfection |
| Solenoid Valve | Automated flow control |

**Estimated Build Cost: ~RM 350** (vs. RM 1,200–3,500 for commercial alternatives)

---

## 🧠 ESP32 Firmware (`ESP32_water_quality.ino`)

### How It Works

The ESP32 firmware runs a continuous 20-second measurement cycle:

1. Reads **pH** via averaged millivolt sampling (50 samples)
2. Reads **Turbidity** via voltage-to-NTU mapping (50 samples)
3. Reads **TDS** using polynomial calibration formula (20 samples)
4. Sends all values to **Blynk** mobile dashboard (virtual pins V0–V4)
5. Uploads data to **ThingSpeak** via HTTP GET request
6. Displays countdown timer to next reading cycle

### Sensor Calibration

```cpp
// pH calibration (linear)
float PH_m = -9.44;
float PH_b = 24.61;
float ph = PH_m * Vph + PH_b;

// Turbidity (voltage to NTU mapping)
// V >= 2.40V → 0 NTU (clear), V <= 1.00V → 300 NTU (dirty)

// TDS (polynomial, 3rd degree)
float tds = (133.42 * Vtds³ - 255.86 * Vtds² + 857.39 * Vtds) * 0.5;
```

### Blynk Virtual Pin Mapping

| Pin | Parameter |
|-----|-----------|
| V0 | pH value |
| V1 | TDS (mg/L) |
| V2 | Turbidity (NTU) |
| V3 | Countdown to next cycle |
| V4 | Status message |

### Setup — Arduino IDE

1. Install **Arduino IDE** and add ESP32 board support
2. Install the following libraries via Library Manager:
   - `Blynk` by Volodymyr Shymanskyy
   - `HTTPClient` (built-in with ESP32)
3. Open `ESP32_water_quality.ino`
4. Update your credentials:

```cpp
// WiFi
const char* WIFI_SSID = "YOUR_WIFI_NAME";
const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";

// Blynk
#define BLYNK_AUTH_TOKEN "YOUR_BLYNK_TOKEN"

// ThingSpeak
const char* TS_WRITE_KEY = "YOUR_THINGSPEAK_KEY";
```

5. Select board: `ESP32 Dev Module`
6. Upload the sketch

---

## 🌐 Web Application (`website.py`)

Built with **Python Flask**, the web dashboard provides:

- Secure user login and registration
- Real-time data retrieval from ThingSpeak API
- **Water Quality Index (WQI)** calculation with grading (A/B/C)
- Interactive bar charts and parameter visualizations (Matplotlib + Seaborn)
- Parameter-specific analysis with recommendations and precautions
- Email report generation (water quality summary with charts)
- Multi-language support via Google Translate
- Machine learning-based water quality predictions (scikit-learn)

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python, Flask, Flask-Login, Flask-Mail |
| Database | SQLite (via SQLAlchemy) |
| Data Viz | Matplotlib, Seaborn |
| ML | scikit-learn |
| IoT Cloud | ThingSpeak API, Blynk |
| Frontend | HTML, CSS, JavaScript |




## 📊 Water Quality Parameters & Safe Ranges

| Parameter | Safe Range | Unit |
|-----------|-----------|------|
| pH | 6.5 – 8.5 | — |
| Turbidity | < 5 | NTU |
| TDS | < 500 | mg/L |

---

## 🧪 Testing Results

| Metric | Result |
|--------|--------|
| pH accuracy | ±0.04 pH (buffer solution test) |
| Sensor stabilization | 5–30 seconds |
| Purification output | ~5 litres / 15 minutes |
| Data transmission | Near real-time (via Blynk) |
| System stability | Stable after hardware improvements |

---

## 🌱 SDG Contributions

- **SDG 6** — Clean Water and Sanitation: Provides safe, verifiable drinking water for off-grid communities
- **SDG 7** — Affordable and Clean Energy: Fully solar-powered with zero grid dependency

---

## 🔮 Future Work

- Integrate **LoRaWAN** for connectivity in deep rural areas without Wi-Fi
- Add **automated pressure sensors** and flow control valves
- Expand ML model for predictive maintenance alerts

---

## 📄 License

This project was developed as part of the EECS2026 Capstone Program at Universiti Teknologi Malaysia. For academic and educational use.

---

*"A reliable, solar-powered system with smart IoT monitoring — delivering safe, affordable, and eco-friendly drinking water."*
