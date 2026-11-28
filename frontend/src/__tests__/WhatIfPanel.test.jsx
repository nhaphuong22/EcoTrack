import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import WhatIfPanel from "../components/dashboard/WhatIfPanel";
import { fetchWhatIf } from "../services/api";

vi.mock("../services/api", () => ({ fetchWhatIf: vi.fn() }));
vi.mock("recharts", async () => {
  const original = await vi.importActual("recharts");
  return {
    ...original,
    ResponsiveContainer: ({ children }) => <div>{children}</div>,
  };
});

const result = (kwhLow, kwhHigh) => ({
  baseline: { kwh: 2400, vnd: 7440000, co2_kg: 1623.84 },
  savings: {
    low: { kwh: kwhLow, vnd: 102300, co2_kg: 22.33 },
    high: { kwh: kwhHigh, vnd: 136400, co2_kg: 29.77 },
  },
  hours: [
    {
      timestamp: "2026-11-28T00:00:00Z",
      vn_hour: 7,
      baseline_kwh: 100,
      scenario_low_kwh: 96,
      scenario_high_kwh: 97,
    },
  ],
  notes: [],
  assumptions: [
    {
      key: "setpoint_rate",
      label: "Mỗi °C nâng setpoint giảm 6–8%",
      value: [0.06, 0.08],
      source: "qcvn_09_2017_hvac.md",
    },
  ],
});

const flush = () => act(() => vi.advanceTimersByTimeAsync(300));
const setpointSlider = () => screen.getByLabelText(/Nâng setpoint/);

describe("WhatIfPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders ranges and assumptions, and debounces slider changes into one request", async () => {
    fetchWhatIf
      .mockResolvedValueOnce(result(0, 0))
      .mockResolvedValueOnce(result(33, 44));
    render(<WhatIfPanel />);
    await flush();
    expect(screen.getByText("0 – 0 kWh")).toBeInTheDocument();
    expect(screen.getByText(/qcvn_09_2017_hvac\.md/)).toBeInTheDocument();
    expect(fetchWhatIf).toHaveBeenCalledWith({
      setpoint_delta_c: 0,
      chiller_off_hours: 0,
      hvac_share: 0.5,
    });

    fireEvent.change(setpointSlider(), { target: { value: "0.5" } });
    fireEvent.change(setpointSlider(), { target: { value: "1" } });
    await act(() => vi.advanceTimersByTimeAsync(299));
    expect(fetchWhatIf).toHaveBeenCalledTimes(1);
    await act(() => vi.advanceTimersByTimeAsync(1));
    expect(fetchWhatIf).toHaveBeenCalledTimes(2);
    expect(fetchWhatIf).toHaveBeenLastCalledWith({
      setpoint_delta_c: 1,
      chiller_off_hours: 0,
      hvac_share: 0.5,
    });
    expect(screen.getByText("33 – 44 kWh")).toBeInTheDocument();
    expect(screen.getByText(/22,3 – 29,8 kg/)).toBeInTheDocument();
  });

  it("ignores an out-of-order response from an older request", async () => {
    let resolveFirst;
    fetchWhatIf
      .mockImplementationOnce(() => new Promise((r) => { resolveFirst = r; }))
      .mockResolvedValueOnce(result(33, 44));
    render(<WhatIfPanel />);
    await flush();
    fireEvent.change(setpointSlider(), { target: { value: "1" } });
    await flush();
    expect(screen.getByText("33 – 44 kWh")).toBeInTheDocument();
    await act(async () => resolveFirst(result(0, 0)));
    expect(screen.queryByText("0 – 0 kWh")).not.toBeInTheDocument();
    expect(screen.getByText("33 – 44 kWh")).toBeInTheDocument();
  });

  it("clears the result and sends no request for an out-of-range HVAC share", async () => {
    fetchWhatIf.mockResolvedValue(result(0, 0));
    render(<WhatIfPanel />);
    await flush();
    expect(screen.getByText("0 – 0 kWh")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/Tỷ trọng HVAC/), { target: { value: "90" } });
    await flush();
    expect(screen.getByText("Nhập từ 5 đến 80.")).toBeInTheDocument();
    expect(screen.queryByText("0 – 0 kWh")).not.toBeInTheDocument();
    expect(fetchWhatIf).toHaveBeenCalledTimes(1);
  });

  it("clears the result and joins validation messages when a request fails", async () => {
    fetchWhatIf
      .mockResolvedValueOnce(result(0, 0))
      .mockRejectedValueOnce({
        message: "Request failed with status code 400",
        response: { data: { detail: [{ msg: "setpoint_delta_c: too big" }, { msg: "hvac_share: too big" }] } },
      });
    render(<WhatIfPanel />);
    await flush();
    fireEvent.change(setpointSlider(), { target: { value: "2" } });
    await flush();
    expect(screen.getByRole("alert")).toHaveTextContent("setpoint_delta_c: too big; hvac_share: too big");
    expect(screen.queryByText("0 – 0 kWh")).not.toBeInTheDocument();
  });
});
