import { Arrow, Box, Diagram, GroupBox, Lifeline, Note, Step } from "@/components/diagram";

/**
 * Năm sơ đồ mô tả cách app hoạt động.
 *
 * Toạ độ tính tay. Khi sửa, giữ ba nguyên tắc:
 *   1. Cách nhau tối thiểu 20px giữa các hộp.
 *   2. Mũi tên đi gấp khúc vuông góc qua vùng trống, không cắt qua hộp.
 *   3. Nhãn mũi tên có nền nên chiếm chỗ thật. Ước lượng bề rộng khoảng
 *      6px mỗi ký tự rồi kiểm tra nó không chồng lên hộp nào.
 *
 * Về hiệu ứng: chỉ bật `animated` cho luồng chính. Cho mọi mũi tên chạy
 * cùng lúc thì sơ đồ thành nhiễu và mắt không biết theo đường nào. `delay`
 * lệch pha để dữ liệu trông như đi lần lượt theo đúng thứ tự thật.
 */

// ═══════════════════════════════════════════════════════════════════════
//  1. Kiến trúc triển khai
// ═══════════════════════════════════════════════════════════════════════

export function DeploymentDiagram() {
  return (
    <Diagram
      step={1}
      title="Kiến trúc triển khai"
      description="Bốn container của profile mặc định, cộng hai profile bật khi cần. Nét chạy đi theo đúng đường một request thật."
      width={920}
      height={600}
      altText="Browser gọi vào web Next.js, web gọi api FastAPI bằng header X-API-Key, api đọc ghi Postgres và Redis. Profile llm chứa LiteLLM gateway được api gọi để dùng model. Profile monitoring chứa Prometheus và Grafana, Prometheus scrape endpoint metrics của api."
      footnote="Mũi tên từ web sang api là lời gọi nội bộ trong mạng docker. Browser không bao giờ gọi api trực tiếp, nên API key không rời khỏi phía server."
    >
      <Box x={380} y={16} w={160} h={40} label="Browser" tone="muted" accentBar={false} />
      <Arrow points={[{ x: 460, y: 56 }, { x: 460, y: 92 }]} animated />

      <Box
        x={340}
        y={92}
        w={240}
        h={76}
        label="web · Next.js"
        lines={["Server Component + Server Action", "giữ CORE_API_KEY"]}
        tone="accent"
        badge=":3000"
        pulse
      />
      <Arrow
        points={[{ x: 460, y: 168 }, { x: 460, y: 206 }]}
        tone="accent"
        label="X-API-Key"
        labelAt={{ x: 472, y: 192 }}
        labelAnchor="start"
        animated
        delay={0.25}
      />

      <Box
        x={340}
        y={206}
        w={240}
        h={76}
        label="api · FastAPI"
        lines={["router → service → model", "/health/* và /metrics mở"]}
        tone="accent"
        badge=":8000"
        pulse
      />

      <Arrow
        points={[
          { x: 460, y: 282 },
          { x: 460, y: 306 },
          { x: 355, y: 306 },
          { x: 355, y: 338 },
        ]}
        animated
        delay={0.5}
      />
      <Arrow
        points={[
          { x: 460, y: 282 },
          { x: 460, y: 306 },
          { x: 555, y: 306 },
          { x: 555, y: 338 },
        ]}
        animated
        delay={0.5}
      />

      <Box
        x={270}
        y={338}
        w={170}
        h={64}
        label="postgres"
        lines={["+ pgvector"]}
        tone="success"
      />
      <Box
        x={480}
        y={338}
        w={150}
        h={64}
        label="redis"
        lines={["cache, rate limit"]}
      />

      {/* ── profile llm ─────────────────────────────────────────────── */}
      <GroupBox x={30} y={440} w={400} h={140} label="profile: llm" tone="warn" />
      <Box
        x={50}
        y={470}
        w={170}
        h={56}
        label="litellm"
        lines={["spend + budget"]}
        tone="warn"
        badge=":4000"
      />
      <Note x={240} y={492}>→ anthropic</Note>
      <Note x={240} y={508}>→ openai, gemini</Note>
      <Note x={240} y={524}>→ ollama (local)</Note>
      <Note x={50} y={558}>Dùng chung Postgres và Redis ở trên</Note>

      {/* Đi vòng bên trái, tránh nhãn của GroupBox nằm ở x 42-129 */}
      <Arrow
        points={[
          { x: 340, y: 244 },
          { x: 16, y: 244 },
          { x: 16, y: 498 },
          { x: 50, y: 498 },
        ]}
        tone="warn"
        label="gọi model qua gateway"
        labelAt={{ x: 180, y: 236 }}
        animated
        delay={0.8}
      />

      {/* ── profile monitoring ──────────────────────────────────────── */}
      <GroupBox x={490} y={440} w={400} h={140} label="profile: monitoring" />
      <Box x={510} y={470} w={160} h={56} label="prometheus" badge=":9090" />
      <Box x={700} y={470} w={160} h={56} label="grafana" badge=":3001" />
      <Note x={510} y={558}>blackbox probe, node và postgres exporter</Note>

      {/* Bắt đầu ở x=650 để không đè lên nhãn "profile: monitoring" */}
      <Arrow
        points={[
          { x: 650, y: 470 },
          { x: 650, y: 424 },
          { x: 900, y: 424 },
          { x: 900, y: 244 },
          { x: 580, y: 244 },
        ]}
        label="scrape /metrics"
        labelAt={{ x: 748, y: 236 }}
        animated
        delay={0.4}
      />
    </Diagram>
  );
}

// ═══════════════════════════════════════════════════════════════════════
//  2. Luồng ghi dữ liệu
// ═══════════════════════════════════════════════════════════════════════

/** Lệch pha giữa các bước. Nhân với chỉ số bước để chúng chạy lần lượt. */
const STEP_STAGGER = 0.7;

export function WriteFlowDiagram() {
  return (
    <Diagram
      step={2}
      title="Luồng ghi dữ liệu"
      description="Ví dụ tạo một task. Từng nét tự vẽ theo đúng thứ tự sáu bước, rồi lặp lại."
      width={900}
      height={330}
      altText="Trình tự sáu bước: browser gọi Server Action, web gửi POST kèm API key lên api, api ghi tasks rồi ghi task_events vào postgres, api trả 201, web gọi revalidatePath và trả payload mới cho browser."
      footnote="Bước 3 và 4 nằm trong cùng một transaction. Session tự commit khi handler chạy xong, tự rollback nếu có exception, nên router không gọi commit thủ công."
    >
      <Lifeline x={110} top={16} bottom={306} label="Browser" sublabel="client" tone="muted" />
      <Lifeline x={340} top={16} bottom={306} label="web" sublabel="Next.js server" tone="accent" />
      <Lifeline x={590} top={16} bottom={306} label="api" sublabel="FastAPI" tone="accent" />
      <Lifeline x={810} top={16} bottom={306} label="postgres" sublabel="database" tone="success" />

      <Step
        step={1}
        from={110}
        to={340}
        y={96}
        label="bấm Thêm, gọi Server Action"
        tone="accent"
        animated
        delay={0}
      />
      <Step
        step={2}
        from={340}
        to={590}
        y={136}
        label="POST /api/v1/tasks + X-API-Key"
        tone="accent"
        animated
        delay={STEP_STAGGER}
      />
      <Step
        step={3}
        from={590}
        to={810}
        y={176}
        label="INSERT tasks"
        tone="success"
        animated
        delay={STEP_STAGGER * 2}
      />
      <Step
        step={4}
        from={590}
        to={810}
        y={212}
        label="INSERT task_events"
        tone="success"
        animated
        delay={STEP_STAGGER * 3}
      />
      <Step
        step={5}
        from={590}
        to={340}
        y={252}
        label="201 TaskDetail"
        animated
        delay={STEP_STAGGER * 4}
      />
      <Step
        step={6}
        from={340}
        to={110}
        y={292}
        label="revalidatePath, RSC payload mới"
        animated
        delay={STEP_STAGGER * 5}
      />
    </Diagram>
  );
}

// ═══════════════════════════════════════════════════════════════════════
//  3. Vòng đời task và thùng rác
// ═══════════════════════════════════════════════════════════════════════

export function TaskLifecycleDiagram() {
  return (
    <Diagram
      step={3}
      title="Vòng đời task và thùng rác"
      description="Nét chạy là đường đi thường gặp nhất. Các nhánh rẽ để tĩnh cho dễ đọc."
      width={920}
      height={400}
      altText="Task đi từ backlog sang todo sang đang làm sang xong. Đang làm và bị chặn chuyển qua lại được. Bị chặn có thể huỷ. Xong mở lại được về todo và completed_at bị xoá. Từ bất kỳ trạng thái, xoá mềm đưa task vào thùng rác, từ đó phục hồi về todo hoặc bị xoá vĩnh viễn sau 30 ngày."
      footnote="Chuyển sang xong thì completed_at được đặt; mở lại thì xoá. Task trong thùng rác không xuất hiện ở agenda, danh sách hay thống kê."
    >
      <Box x={40} y={64} w={130} h={48} label="backlog" tone="muted" accentBar={false} />
      <Box x={230} y={64} w={130} h={48} label="todo" />
      <Box x={420} y={64} w={150} h={48} label="in_progress" tone="warn" pulse />
      {/* done đẩy sang 680 để nhãn "completed_at" có chỗ đứng giữa hai hộp */}
      <Box x={680} y={64} w={130} h={48} label="done" tone="success" />
      <Box x={420} y={170} w={150} h={48} label="blocked" tone="danger" />
      <Box x={680} y={170} w={130} h={48} label="cancelled" tone="muted" accentBar={false} />

      {/* Đường đi thường gặp: backlog → todo → in_progress → done */}
      <Arrow points={[{ x: 170, y: 88 }, { x: 230, y: 88 }]} animated />
      <Arrow points={[{ x: 360, y: 88 }, { x: 420, y: 88 }]} animated delay={0.3} />
      <Arrow
        points={[{ x: 570, y: 88 }, { x: 680, y: 88 }]}
        tone="success"
        label="completed_at"
        labelAt={{ x: 625, y: 80 }}
        animated
        delay={0.6}
      />

      {/* Nhánh rẽ: để tĩnh, nếu cũng chạy thì mắt không biết theo đường nào */}
      <Arrow
        points={[{ x: 495, y: 112 }, { x: 495, y: 170 }]}
        bidirectional
        tone="danger"
      />
      <Arrow
        points={[{ x: 570, y: 194 }, { x: 680, y: 194 }]}
        label="huỷ"
        labelAt={{ x: 625, y: 186 }}
      />

      {/* Mở lại: đi vòng phía trên để không cắt qua hộp nào */}
      <Arrow
        points={[
          { x: 745, y: 64 },
          { x: 745, y: 28 },
          { x: 295, y: 28 },
          { x: 295, y: 64 },
        ]}
        label="mở lại, completed_at = null"
        labelAt={{ x: 520, y: 22 }}
      />

      {/* Thùng rác */}
      <Box
        x={330}
        y={286}
        w={220}
        h={56}
        label="thùng rác"
        lines={["deleted_at khác null"]}
        tone="danger"
        dashed
      />

      {/* Vòng xoá và phục hồi: chạy để thấy đây là đường hai chiều */}
      <Arrow
        points={[{ x: 470, y: 218 }, { x: 470, y: 286 }]}
        tone="danger"
        label="xoá mềm"
        labelAt={{ x: 480, y: 256 }}
        labelAnchor="start"
        animated
        delay={0.9}
      />

      <Arrow
        points={[
          { x: 330, y: 314 },
          { x: 200, y: 314 },
          { x: 200, y: 112 },
          { x: 295, y: 112 },
        ]}
        tone="success"
        label="phục hồi"
        labelAt={{ x: 210, y: 200 }}
        labelAnchor="start"
        animated
        delay={1.2}
      />

      <Arrow points={[{ x: 550, y: 314 }, { x: 700, y: 314 }]} tone="danger" />
      <Note x={562} y={302}>xoá vĩnh viễn sau 30 ngày</Note>
      <Note x={562} y={336}>dọn khi khởi động hoặc mở tab Thùng rác</Note>
    </Diagram>
  );
}

// ═══════════════════════════════════════════════════════════════════════
//  4. Ba nguồn dữ liệu
// ═══════════════════════════════════════════════════════════════════════

export function DataSourceDiagram() {
  return (
    <Diagram
      step={4}
      title="Ba nguồn dữ liệu"
      description="lib/api.ts là cửa duy nhất. Chữ ký hàm giống nhau ở cả ba chế độ nên page không cần biết dữ liệu nằm ở đâu."
      width={900}
      height={340}
      altText="Page và Server Action gọi lib/api.ts. File này điều phối theo biến DATA_SOURCE sang ba đích: file JSON trên đĩa, bộ nhớ tạm, hoặc core API và Postgres."
      footnote="Đổi chế độ là đổi một biến môi trường, không sửa code. Đây cũng là đường chuyển dữ liệu từ file lên Postgres: xuất JSON ở chế độ file, đổi sang api, rồi nhập lại."
    >
      <Box
        x={330}
        y={16}
        w={240}
        h={56}
        label="Page + Server Action"
        lines={["gọi hàm chung"]}
        tone="muted"
        accentBar={false}
      />
      <Arrow points={[{ x: 450, y: 72 }, { x: 450, y: 106 }]} animated />

      <Box
        x={310}
        y={106}
        w={280}
        h={60}
        label="lib/api.ts"
        lines={["điều phối theo DATA_SOURCE"]}
        tone="accent"
        pulse
      />

      <Arrow
        points={[
          { x: 450, y: 166 },
          { x: 450, y: 200 },
          { x: 140, y: 200 },
          { x: 140, y: 234 },
        ]}
        animated
        delay={0.35}
      />
      <Arrow
        points={[{ x: 450, y: 166 }, { x: 450, y: 234 }]}
        animated
        delay={0.35}
      />
      <Arrow
        points={[
          { x: 450, y: 166 },
          { x: 450, y: 200 },
          { x: 760, y: 200 },
          { x: 760, y: 234 },
        ]}
        tone="success"
        animated
        delay={0.35}
      />

      <Box
        x={40}
        y={234}
        w={200}
        h={76}
        label="= file"
        lines={["store/engine + JSON", "data/builder-data.json"]}
      />
      <Box
        x={350}
        y={234}
        w={200}
        h={76}
        label="= memory"
        lines={["store/engine", "mất khi restart"]}
        tone="muted"
        accentBar={false}
      />
      <Box
        x={660}
        y={234}
        w={200}
        h={76}
        label="= api"
        lines={["core API → Postgres", "chế độ thật"]}
        tone="success"
      />
    </Diagram>
  );
}

// ═══════════════════════════════════════════════════════════════════════
//  5. Phân lớp backend
// ═══════════════════════════════════════════════════════════════════════

export function BackendLayersDiagram() {
  return (
    <Diagram
      step={5}
      title="Phân lớp backend"
      description="Router chỉ parse và serialize. Toàn bộ logic nằm ở service, nên agent và MCP server dùng lại được mà không kéo theo FastAPI."
      width={860}
      height={390}
      altText="Request đi từ router.py xuống các file route, xuống tầng service, xuống models. Tầng service ném DomainError và được main.py map sang HTTP status."
      footnote="Service layer không biết gì về HTTP. Đó là lý do một exception handler duy nhất ở main.py đủ để map toàn bộ lỗi nghiệp vụ."
    >
      <Box
        x={100}
        y={20}
        w={520}
        h={56}
        label="api/v1/router.py"
        lines={["gắn require_api_key cho toàn bộ /api/v1"]}
        tone="accent"
      />
      <Arrow points={[{ x: 360, y: 76 }, { x: 360, y: 106 }]} tone="accent" animated />

      <Box
        x={100}
        y={106}
        w={520}
        h={72}
        label="api/v1/tasks.py · projects.py"
        lines={[
          "parse query param, gọi service, serialize response",
          "route tĩnh (/agenda, /stats, /trash) khai báo TRƯỚC /{task_id}",
        ]}
      />
      <Arrow points={[{ x: 360, y: 178 }, { x: 360, y: 208 }]} animated delay={0.3} />

      <Box
        x={100}
        y={208}
        w={520}
        h={72}
        label="services/"
        lines={[
          "filter, sắp xếp, side effect chuyển trạng thái, thùng rác",
          "ném DomainError, không biết gì về HTTP",
        ]}
        tone="warn"
        pulse
      />
      <Arrow points={[{ x: 360, y: 280 }, { x: 360, y: 310 }]} tone="warn" animated delay={0.6} />

      <Box
        x={100}
        y={310}
        w={520}
        h={64}
        label="models/"
        lines={["constraint và index khai báo ở đây", "không create_all, chỉ Alembic"]}
        tone="success"
      />

      <Box
        x={660}
        y={208}
        w={180}
        h={72}
        label="main.py"
        lines={["một exception handler", "DomainError → HTTP"]}
        tone="muted"
        dashed
      />
      <Arrow
        points={[{ x: 620, y: 244 }, { x: 660, y: 244 }]}
        tone="warn"
        animated
        delay={0.9}
      />
    </Diagram>
  );
}
