import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ChatMessage from '../components/copilot/ChatMessage';
import CopilotDrawer from '../components/copilot/CopilotDrawer';

describe('Story 3.6: Copilot Markdown, Sources, and Streaming UI', () => {
  it('renders markdown tables, headings, and lists correctly in assistant bubble', () => {
    const message = {
      role: 'assistant',
      content: `### Báo cáo năng lượng
| Khu vực | Tiêu thụ (kWh) |
| --- | --- |
| Zone 1 | 120 |
| Zone 2 | 85 |

- Đèn LED: Đạt chuẩn QCVN 09:2017
- Chiller: Cần tối ưu setpoint`,
      tools_used: ['domain_knowledge', 'query_metrics'],
      sources: [
        {
          title: 'QCVN 09:2017/BXD',
          source: 'qcvn09_envelope.md',
          snippet: 'Quy chuẩn kỹ thuật quốc gia về các công trình xây dựng sử dụng năng lượng hiệu quả.',
        },
      ],
    };

    render(<ChatMessage message={message} />);

    // Check headings
    expect(screen.getByText('Báo cáo năng lượng')).toBeInTheDocument();

    // Check table headers and cells
    expect(screen.getByText('Khu vực')).toBeInTheDocument();
    expect(screen.getByText('Tiêu thụ (kWh)')).toBeInTheDocument();
    expect(screen.getByText('Zone 1')).toBeInTheDocument();
    expect(screen.getByText('120')).toBeInTheDocument();

    // Check list items
    expect(screen.getByText(/Đèn LED: Đạt chuẩn QCVN 09:2017/)).toBeInTheDocument();

    // Check tool badges
    expect(screen.getByText(/domain_knowledge/)).toBeInTheDocument();
    expect(screen.getByText(/query_metrics/)).toBeInTheDocument();

    // Check sources
    expect(screen.getByText(/Tài liệu trích dẫn/)).toBeInTheDocument();
    expect(screen.getByText('QCVN 09:2017/BXD')).toBeInTheDocument();
    expect(screen.getByText('qcvn09_envelope.md')).toBeInTheDocument();
    expect(screen.getByText(/Quy chuẩn kỹ thuật quốc gia/)).toBeInTheDocument();
  });

  it('renders Stop button when isLoading is true and triggers stopStreaming on click', () => {
    const handleStop = vi.fn();
    render(
      <CopilotDrawer
        isOpen={true}
        onClose={vi.fn()}
        messages={[{ role: 'assistant', content: 'Đang tạo nội dung...' }]}
        isLoading={true}
        stopStreaming={handleStop}
        sendMessage={vi.fn()}
      />
    );

    const stopBtns = screen.getAllByRole('button', { name: /dừng/i });
    expect(stopBtns.length).toBeGreaterThan(0);
    fireEvent.click(stopBtns[0]);
    expect(handleStop).toHaveBeenCalledTimes(1);
  });

  it('renders error message and retry action when error occurs', () => {
    const handleRetry = vi.fn();
    render(
      <CopilotDrawer
        isOpen={true}
        onClose={vi.fn()}
        messages={[]}
        error="Mất kết nối với AI service"
        retry={handleRetry}
        sendMessage={vi.fn()}
      />
    );

    expect(screen.getByText('Mất kết nối với AI service')).toBeInTheDocument();
    const retryBtn = screen.getByRole('button', { name: /thử lại/i });
    expect(retryBtn).toBeInTheDocument();
    fireEvent.click(retryBtn);
    expect(handleRetry).toHaveBeenCalledTimes(1);
  });
});
