import React from "react";

/**
 * PriceTable — renders structured price comparison.
 *
 * Layout (2 sections):
 * - Internal: hero cards with database values (prominent)
 * - External: collapsible comparison list from web (subtle)
 *
 * Each card shows: field_label, price (full), date, source.
 */
export default function PriceTable({ rows, intent }) {
  if (!rows || rows.length === 0) return null;

  const internal = rows.filter((r) => r.type === "internal");
  const external = rows.filter((r) => r.type === "external");

  return (
    <div className="price-table-wrapper">
      {intent && <IntentBadge intent={intent} />}

      {/* Section 1: Internal (hero) */}
      {internal.length > 0 && (
        <section className="price-internal-section">
          <h4 className="section-title">
            <span className="section-icon">📊</span> Data Internal
          </h4>
          <div className="internal-list">
            {internal.map((r, i) => (
              <InternalCard key={`int-${i}`} row={r} />
            ))}
          </div>
        </section>
      )}

      {/* Section 2: External (collapsible) */}
      {external.length > 0 && (
        <details className="price-external-section" open>
          <summary>
            <span className="section-icon">🌐</span> Pembanding Web ({external.length})
          </summary>
          <div className="external-list">
            {external.map((r, i) => (
              <ExternalCard key={`ext-${i}`} row={r} />
            ))}
          </div>
        </details>
      )}

      <div className="price-disclaimer">
        ⚠️ Harga dapat berubah sewaktu-waktu. Selalu verifikasi ke sumber resmi.
      </div>
    </div>
  );
}

function IntentBadge({ intent }) {
  const typeIcons = {
    catalog: "📦",
    timeseries: "📅",
    range: "📊",
    multi_criteria: "🔍",
  };
  const icon = typeIcons[intent.type] || "💰";
  const parts = [];
  if (intent.field_label) parts.push(intent.field_label);
  if (intent.target) parts.push(intent.target);
  if (intent.date) parts.push(`pada ${formatDateId(intent.date)}`);
  if (intent.date_range_start && intent.date_range_end) {
    parts.push(
      `${formatDateId(intent.date_range_start)} – ${formatDateId(intent.date_range_end)}`
    );
  }
  if (intent.currency && intent.currency !== "IDR") {
    parts.push(`(${intent.currency})`);
  }
  return (
    <div className="price-intent-badge">
      {icon} {parts.join(" · ")}
    </div>
  );
}

function InternalCard({ row }) {
  return (
    <div className="price-card internal">
      {row.field_label && (
        <span className="field-label">{row.field_label}</span>
      )}
      <div className="product-name">{row.product}</div>
      <div className="price-value">{row.price}</div>
      <div className="meta">
        {row.date && <span className="date">📅 {row.date}</span>}
        {row.unit && row.unit !== "-" && (
          <span className="unit">per {row.unit}</span>
        )}
        <span className="source">🗄️ {row.source}</span>
      </div>
    </div>
  );
}

function ExternalCard({ row }) {
  const Wrapper = row.url ? "a" : "div";
  const wrapperProps = row.url
    ? { href: row.url, target: "_blank", rel: "noreferrer" }
    : {};

  return (
    <Wrapper
      {...wrapperProps}
      className={`price-card external ${row.url ? "clickable" : ""}`}
    >
      {row.field_label && (
        <span className="field-label small">{row.field_label}</span>
      )}
      <div className="product-name">{row.product}</div>
      <div className="price-value">{row.price}</div>
      <div className="meta">
        {row.date && row.date !== "recent" && (
          <span className="date">{row.date}</span>
        )}
        <span className="source">{truncate(row.source, 50)}</span>
        {row.url && <span className="external-link">↗</span>}
      </div>
    </Wrapper>
  );
}

function formatDateId(iso) {
  if (!iso) return "";
  if (iso.includes("Q")) {
    return iso.replace("-Q", " Q");
  }
  if (iso.includes("/")) {
    const [s, e] = iso.split("/");
    return `${formatDateId(s)} – ${formatDateId(e)}`;
  }
  try {
    const parts = iso.split("-");
    if (parts.length === 3) {
      const months = [
        "", "Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
        "Jul", "Agu", "Sep", "Okt", "Nov", "Des",
      ];
      return `${parseInt(parts[2])} ${months[parseInt(parts[1])]} ${parts[0]}`;
    }
  } catch {
    return iso;
  }
  return iso;
}

function truncate(text, n) {
  if (!text) return "";
  return text.length > n ? text.substring(0, n) + "…" : text;
}
