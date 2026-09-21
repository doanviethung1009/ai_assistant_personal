import type { ReactNode } from "react";

/**
 * Bộ primitive để vẽ sơ đồ bằng SVG thuần.
 *
 * Không dùng thư viện diagram vì ba lý do: không thêm dependency, chạy được
 * trong Server Component (chỉ xuất SVG tĩnh), và kiểm soát được chính xác vị
 * trí mũi tên. Đổi lại phải tự tính toạ độ.
 *
 * Quy ước toạ độ: mỗi sơ đồ khai báo viewBox riêng, bọc trong khung cuộn
 * ngang để màn hình nhỏ không làm méo hình.
 */

export type Tone = "default" | "accent" | "success" | "warn" | "danger" | "muted";

const FILL: Record<Tone, string> = {
  default: "var(--color-surface-raised)",
  accent: "color-mix(in srgb, var(--color-accent) 16%, var(--color-surface))",
  success: "color-mix(in srgb, var(--color-success) 16%, var(--color-surface))",
  warn: "color-mix(in srgb, var(--color-warn) 16%, var(--color-surface))",
  danger: "color-mix(in srgb, var(--color-danger) 16%, var(--color-surface))",
  muted: "var(--color-surface)",
};

const STROKE: Record<Tone, string> = {
  default: "var(--color-border)",
  accent: "var(--color-accent)",
  success: "var(--color-success)",
  warn: "var(--color-warn)",
  danger: "var(--color-danger)",
  muted: "var(--color-border)",
};

/** Màu vạch nhấn bên trái hộp. Đậm hơn viền để tạo điểm nhìn. */
const ACCENT_BAR: Record<Tone, string> = {
  default: "var(--color-ink-muted)",
  accent: "var(--color-accent)",
  success: "var(--color-success)",
  warn: "var(--color-warn)",
  danger: "var(--color-danger)",
  muted: "var(--color-border)",
};

const LABEL_COLOR = "var(--color-ink)";
const MUTED_COLOR = "var(--color-ink-muted)";
const SURFACE = "var(--color-surface)";

const TONES: Tone[] = ["default", "accent", "success", "warn", "danger", "muted"];

/** Màu nét vẽ của mũi tên theo tone. */
function arrowColor(tone: Tone): string {
  return tone === "default" || tone === "muted" ? MUTED_COLOR : STROKE[tone];
}

/**
 * Ước lượng bề rộng chuỗi để vẽ nền cho nhãn.
 *
 * SVG không tự đo text nên phải đoán. 5.95px mỗi ký tự là số đo thực nghiệm
 * cho font hệ thống ở cỡ 11px với tiếng Việt có dấu. Thà rộng hơn một chút
 * còn hơn để chữ tràn ra ngoài nền.
 */
function estimateTextWidth(text: string, fontSize = 11): number {
  return text.length * fontSize * 0.54;
}

// ── Định nghĩa dùng chung ──────────────────────────────────────────────

/**
 * Marker mũi tên và filter đổ bóng, render MỘT LẦN cho cả trang.
 *
 * Hai lý do không đặt trong từng sơ đồ: id trùng nhau giữa nhiều thẻ svg là
 * HTML không hợp lệ, và `fill="context-stroke"` chưa được hỗ trợ đồng đều nên
 * ở đây mỗi tone có marker riêng với màu ghi cứng.
 */
export function DiagramDefs() {
  return (
    <svg width={0} height={0} aria-hidden="true" className="absolute">
      <defs>
        <filter id="diagram-shadow" x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow
            dx="0"
            dy="2"
            stdDeviation="3"
            floodColor="#000"
            floodOpacity="0.35"
          />
        </filter>

        {TONES.map((tone) => {
          const color = arrowColor(tone);
          return (
            <g key={tone}>
              <marker
                id={`arrow-end-${tone}`}
                viewBox="0 0 12 12"
                refX="10"
                refY="6"
                markerWidth="7"
                markerHeight="7"
                orient="auto"
              >
                {/* Đầu mũi tên hơi lõm đuôi cho gọn mắt hơn tam giác đặc */}
                <path d="M 1 1 L 11 6 L 1 11 L 3.5 6 Z" fill={color} />
              </marker>
              <marker
                id={`arrow-start-${tone}`}
                viewBox="0 0 12 12"
                refX="2"
                refY="6"
                markerWidth="7"
                markerHeight="7"
                orient="auto"
              >
                <path d="M 11 1 L 1 6 L 11 11 L 8.5 6 Z" fill={color} />
              </marker>
            </g>
          );
        })}
      </defs>
    </svg>
  );
}

// ── Khung sơ đồ ────────────────────────────────────────────────────────

export function Diagram({
  title,
  description,
  width,
  height,
  altText,
  children,
  footnote,
  step,
}: {
  title: string;
  description?: string;
  width: number;
  height: number;
  /** Mô tả cho screen reader, vì sơ đồ SVG không tự đọc được. */
  altText: string;
  children: ReactNode;
  footnote?: ReactNode;
  /** Số thứ tự hiện ở góc, giúp trỏ nhanh khi trao đổi. */
  step?: number;
}) {
  return (
    <figure className="overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-raised)]">
      <figcaption className="border-b border-[var(--color-border)] bg-white/[0.02] px-4 py-3">
        <div className="flex items-start gap-2.5">
          {step !== undefined ? (
            <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-md bg-[var(--color-accent)]/15 text-xs font-semibold text-[var(--color-accent)]">
              {step}
            </span>
          ) : null}
          <div className="min-w-0">
            <h3 className="text-sm font-semibold tracking-tight">{title}</h3>
            {description ? (
              <p className="mt-1 text-xs leading-relaxed text-[var(--color-ink-muted)]">
                {description}
              </p>
            ) : null}
          </div>
        </div>
      </figcaption>

      <div className="overflow-x-auto px-4 py-4">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          width={width}
          height={height}
          role="img"
          aria-label={altText}
          className="h-auto max-w-none"
          style={{ minWidth: Math.min(width, 620) }}
        >
          {children}
        </svg>
      </div>

      {footnote ? (
        <p className="border-t border-[var(--color-border)] bg-white/[0.02] px-4 py-3 text-xs leading-relaxed text-[var(--color-ink-muted)]">
          {footnote}
        </p>
      ) : null}
    </figure>
  );
}

// ── Hộp ────────────────────────────────────────────────────────────────

export function Box({
  x,
  y,
  w,
  h,
  label,
  lines = [],
  tone = "default",
  dashed = false,
  badge,
  accentBar = true,
  pulse = false,
}: {
  x: number;
  y: number;
  w: number;
  h: number;
  label: string;
  /** Các dòng phụ dưới nhãn chính. Giữ ngắn vì SVG không tự wrap. */
  lines?: string[];
  tone?: Tone;
  dashed?: boolean;
  /** Nhãn nhỏ ở góc trên phải, ví dụ số cổng. */
  badge?: string;
  accentBar?: boolean;
  /** Hào quang thở, dùng cho node chính của luồng. */
  pulse?: boolean;
}) {
  const hasLines = lines.length > 0;
  const labelY = hasLines ? y + 24 : y + h / 2 + 4.5;
  const badgeWidth = badge ? estimateTextWidth(badge, 10) + 12 : 0;

  return (
    <g>
      {pulse ? (
        <rect
          x={x - 5}
          y={y - 5}
          width={w + 10}
          height={h + 10}
          rx={14}
          fill="none"
          stroke={STROKE[tone]}
          strokeWidth={2}
          className="diagram-breathe"
        />
      ) : null}

      <rect
        x={x}
        y={y}
        width={w}
        height={h}
        rx={10}
        fill={FILL[tone]}
        stroke={STROKE[tone]}
        strokeWidth={1.5}
        strokeDasharray={dashed ? "5 4" : undefined}
        filter={dashed ? undefined : "url(#diagram-shadow)"}
      />

      {/* Vạch nhấn bên trái, bo theo góc hộp */}
      {accentBar && !dashed ? (
        <path
          d={`M ${x + 1} ${y + 10} a 9 9 0 0 1 3 -8.4 L ${x + 4} ${y + h - 1.6} a 9 9 0 0 1 -3 -8.4 Z`}
          fill={ACCENT_BAR[tone]}
          opacity={0.9}
        />
      ) : null}

      {badge ? (
        <g>
          <rect
            x={x + w - badgeWidth - 8}
            y={y + 7}
            width={badgeWidth}
            height={16}
            rx={8}
            fill="rgba(255,255,255,0.06)"
          />
          <text
            x={x + w - badgeWidth / 2 - 8}
            y={y + 18.5}
            textAnchor="middle"
            fontSize={10}
            fill={MUTED_COLOR}
          >
            {badge}
          </text>
        </g>
      ) : null}

      <text
        x={x + w / 2}
        y={labelY}
        textAnchor="middle"
        fontSize={13}
        fontWeight={600}
        fill={LABEL_COLOR}
      >
        {label}
      </text>

      {lines.map((line, index) => (
        <text
          key={line}
          x={x + w / 2}
          y={labelY + 17 + index * 14}
          textAnchor="middle"
          fontSize={11}
          fill={MUTED_COLOR}
        >
          {line}
        </text>
      ))}
    </g>
  );
}

/** Khung gạch đứt để nhóm nhiều hộp, kèm nhãn ở góc trên. */
export function GroupBox({
  x,
  y,
  w,
  h,
  label,
  tone = "muted",
}: {
  x: number;
  y: number;
  w: number;
  h: number;
  label: string;
  tone?: Tone;
}) {
  const labelWidth = estimateTextWidth(label, 11) + 16;

  return (
    <g>
      <rect
        x={x}
        y={y}
        width={w}
        height={h}
        rx={12}
        fill="rgba(255,255,255,0.015)"
        stroke={STROKE[tone]}
        strokeWidth={1.5}
        strokeDasharray="7 6"
      />
      {/* Nền cho nhãn để nó không chồng lên nét gạch đứt */}
      <rect
        x={x + 12}
        y={y - 8}
        width={labelWidth}
        height={17}
        rx={8}
        fill={SURFACE}
        stroke={STROKE[tone]}
        strokeWidth={1}
      />
      <text
        x={x + 12 + labelWidth / 2}
        y={y + 4}
        textAnchor="middle"
        fontSize={11}
        fontWeight={600}
        fill={MUTED_COLOR}
      >
        {label}
      </text>
    </g>
  );
}

// ── Nhãn có nền ────────────────────────────────────────────────────────

/**
 * Chữ có nền mờ phía sau.
 *
 * Đây là cải thiện đáng kể nhất về độ dễ đọc: nhãn mũi tên nằm đè lên nét vẽ,
 * không có nền thì chữ và đường kẻ trộn vào nhau.
 */
function PillText({
  x,
  y,
  text,
  anchor = "middle",
  color = MUTED_COLOR,
  fontSize = 11,
  weight = 400,
}: {
  x: number;
  y: number;
  text: string;
  anchor?: "start" | "middle" | "end";
  color?: string;
  fontSize?: number;
  weight?: number;
}) {
  const width = estimateTextWidth(text, fontSize) + 12;
  const height = fontSize + 8;
  const rectX = anchor === "middle" ? x - width / 2 : anchor === "end" ? x - width : x - 6;

  return (
    <g>
      <rect
        x={rectX}
        y={y - height + 4}
        width={width}
        height={height}
        rx={height / 2}
        fill={SURFACE}
        opacity={0.92}
      />
      <text
        x={x}
        y={y}
        textAnchor={anchor}
        fontSize={fontSize}
        fontWeight={weight}
        fill={color}
      >
        {text}
      </text>
    </g>
  );
}

// ── Mũi tên ────────────────────────────────────────────────────────────

export interface Point {
  x: number;
  y: number;
}

export function Arrow({
  points,
  tone = "default",
  label,
  labelAt,
  labelAnchor = "middle",
  bidirectional = false,
  dashed = false,
  animated = false,
  delay = 0,
}: {
  /** Ít nhất hai điểm. Nhiều điểm sẽ vẽ đường gấp khúc bo góc. */
  points: Point[];
  tone?: Tone;
  label?: string;
  /** Vị trí nhãn. Không truyền thì đặt ở giữa đoạn đầu. */
  labelAt?: Point;
  labelAnchor?: "start" | "middle" | "end";
  bidirectional?: boolean;
  dashed?: boolean;
  /** Nét chạy theo hướng mũi tên, cho thấy dữ liệu đang di chuyển. */
  animated?: boolean;
  /** Lệch pha so với các mũi tên khác, để mắt đi theo đúng thứ tự. */
  delay?: number;
}) {
  const first = points[0]!;
  const second = points[1] ?? first;
  const anchor = labelAt ?? {
    x: (first.x + second.x) / 2,
    y: (first.y + second.y) / 2 - 6,
  };
  const stroke = arrowColor(tone);

  return (
    <g>
      <path
        d={roundedPath(points, 10)}
        fill="none"
        stroke={stroke}
        strokeWidth={1.75}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeDasharray={dashed && !animated ? "5 5" : undefined}
        markerEnd={`url(#arrow-end-${tone})`}
        markerStart={bidirectional ? `url(#arrow-start-${tone})` : undefined}
        className={animated ? "diagram-flow" : undefined}
        style={animated && delay ? { animationDelay: `${delay}s` } : undefined}
      />
      {label ? (
        <PillText
          x={anchor.x}
          y={anchor.y}
          text={label}
          anchor={labelAnchor}
          color={tone === "default" || tone === "muted" ? MUTED_COLOR : STROKE[tone]}
        />
      ) : null}
    </g>
  );
}

/**
 * Dựng path gấp khúc có góc bo.
 *
 * Đường gấp khúc góc vuông trông thô; bo 10px ở mỗi khúc rẽ làm sơ đồ mềm hẳn.
 * Bán kính tự thu lại nếu đoạn quá ngắn để không bị vặn hình.
 */
function roundedPath(points: Point[], radius: number): string {
  if (points.length < 2) return "";
  if (points.length === 2) {
    return `M ${points[0]!.x} ${points[0]!.y} L ${points[1]!.x} ${points[1]!.y}`;
  }

  let path = `M ${points[0]!.x} ${points[0]!.y}`;

  for (let index = 1; index < points.length - 1; index += 1) {
    const previous = points[index - 1]!;
    const corner = points[index]!;
    const next = points[index + 1]!;

    const inLength = Math.hypot(corner.x - previous.x, corner.y - previous.y);
    const outLength = Math.hypot(next.x - corner.x, next.y - corner.y);
    const r = Math.min(radius, inLength / 2, outLength / 2);

    const inRatio = inLength === 0 ? 0 : r / inLength;
    const outRatio = outLength === 0 ? 0 : r / outLength;

    const entry = {
      x: corner.x - (corner.x - previous.x) * inRatio,
      y: corner.y - (corner.y - previous.y) * inRatio,
    };
    const exit = {
      x: corner.x + (next.x - corner.x) * outRatio,
      y: corner.y + (next.y - corner.y) * outRatio,
    };

    path += ` L ${entry.x} ${entry.y} Q ${corner.x} ${corner.y} ${exit.x} ${exit.y}`;
  }

  const last = points[points.length - 1]!;
  path += ` L ${last.x} ${last.y}`;
  return path;
}

/** Nhãn rời, dùng cho ghi chú trong sơ đồ. */
export function Note({
  x,
  y,
  children,
  anchor = "start",
  tone = "muted",
  pill = false,
}: {
  x: number;
  y: number;
  children: string;
  anchor?: "start" | "middle" | "end";
  tone?: "muted" | "ink";
  pill?: boolean;
}) {
  const color = tone === "ink" ? LABEL_COLOR : MUTED_COLOR;

  if (pill) {
    return <PillText x={x} y={y} text={children} anchor={anchor} color={color} />;
  }

  return (
    <text x={x} y={y} textAnchor={anchor} fontSize={11} fill={color}>
      {children}
    </text>
  );
}

/** Đường kẻ dọc của sequence diagram. */
export function Lifeline({
  x,
  top,
  bottom,
  label,
  sublabel,
  tone = "default",
}: {
  x: number;
  top: number;
  bottom: number;
  label: string;
  sublabel?: string;
  tone?: Tone;
}) {
  const boxHeight = sublabel ? 46 : 34;

  return (
    <g>
      {/* Dải mờ chạy dọc giúp mắt theo đúng cột */}
      <rect
        x={x - 70}
        y={top}
        width={140}
        height={bottom - top}
        rx={10}
        fill="rgba(255,255,255,0.012)"
      />
      <rect
        x={x - 70}
        y={top}
        width={140}
        height={boxHeight}
        rx={9}
        fill={FILL[tone]}
        stroke={STROKE[tone]}
        strokeWidth={1.5}
        filter="url(#diagram-shadow)"
      />
      <text
        x={x}
        y={top + (sublabel ? 20 : 22)}
        textAnchor="middle"
        fontSize={12.5}
        fontWeight={600}
        fill={LABEL_COLOR}
      >
        {label}
      </text>
      {sublabel ? (
        <text x={x} y={top + 36} textAnchor="middle" fontSize={10} fill={MUTED_COLOR}>
          {sublabel}
        </text>
      ) : null}
      <line
        x1={x}
        y1={top + boxHeight}
        x2={x}
        y2={bottom}
        stroke={STROKE.default}
        strokeWidth={1}
        strokeDasharray="3 5"
      />
    </g>
  );
}

/** Một bước trong sequence diagram: mũi tên ngang có số thứ tự. */
export function Step({
  from,
  to,
  y,
  step,
  label,
  tone = "default",
  dashed = false,
  animated = false,
  /** Lệch pha, thường là (step - 1) * 0.7 để các bước chạy lần lượt. */
  delay = 0,
}: {
  from: number;
  to: number;
  y: number;
  step: number;
  label: string;
  tone?: Tone;
  dashed?: boolean;
  animated?: boolean;
  delay?: number;
}) {
  const stroke = arrowColor(tone);
  const badgeColor = STROKE[tone === "default" ? "accent" : tone];
  const midpoint = (from + to) / 2;
  const length = Math.abs(to - from);

  // stroke-dasharray bằng đúng độ dài nét, rồi kéo dashoffset về 0 để nét
  // tự vẽ ra. Truyền độ dài qua CSS custom property vì keyframes cần nó.
  const traceStyle = {
    "--trace-len": String(length),
    animationDelay: `${delay}s`,
  } as React.CSSProperties;

  return (
    <g>
      <line
        x1={from}
        y1={y}
        x2={to}
        y2={y}
        stroke={stroke}
        strokeWidth={1.75}
        strokeLinecap="round"
        strokeDasharray={dashed && !animated ? "5 5" : undefined}
        markerEnd={`url(#arrow-end-${tone})`}
        className={animated ? "diagram-trace" : undefined}
        style={animated ? traceStyle : undefined}
      />

      <PillText x={midpoint} y={y - 9} text={label} anchor="middle" />

      {/* Vòng nền để số không lẫn vào đường kẻ phía sau */}
      <g
        className={animated ? "diagram-step-glow" : undefined}
        style={animated ? { animationDelay: `${delay}s` } : undefined}
      >
        <circle cx={from} cy={y} r={11} fill={SURFACE} />
        <circle cx={from} cy={y} r={9} fill={badgeColor} />
        <text
          x={from}
          y={y + 3.5}
          textAnchor="middle"
          fontSize={10}
          fontWeight={700}
          fill={SURFACE}
        >
          {step}
        </text>
      </g>
    </g>
  );
}
