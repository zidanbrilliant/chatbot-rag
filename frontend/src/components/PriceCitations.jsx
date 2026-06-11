import React from "react";

/**
 * PriceCitations — renders the source list at the bottom of an NL response.
 *
 * Each source has a stable ID [1], [2], ... referenced inline in the LLM answer.
 * Shows source label, price, and clickable URL for external sources.
 */
export default function PriceCitations({ sources, intent }) {
  if (!sources || sources.length === 0) return null;

  const internalCount = sources.filter((s) => s.type === "internal").length;
  const externalCount = sources.filter((s) => s.type === "external").length;

  return (
    <div className="price-citations-wrapper">
      {intent && (
        <div className="citations-header">
          <span className="citations-icon">📚</span>
          <strong>Sumber ({sources.length})</strong>
          {internalCount > 0 && (
            <span className="source-stat">🗄️ {internalCount} database</span>
          )}
          {externalCount > 0 && (
            <span className="source-stat">🌐 {externalCount} web</span>
          )}
        </div>
      )}

      <div className="sources-list">
        {sources.map((s) => (
          <SourceCard key={s.id} source={s} />
        ))}
      </div>
    </div>
  );
}

function SourceCard({ source }) {
  const Wrapper = source.url ? "a" : "div";
  const wrapperProps = source.url
    ? { href: source.url, target: "_blank", rel: "noreferrer" }
    : {};

  return (
    <Wrapper
      {...wrapperProps}
      className={`source-card source-${source.type} ${
        source.url ? "clickable" : ""
      }`}
    >
      <span className="source-marker">[{source.id}]</span>
      <div className="source-content">
        <div className="source-label-row">
          <span className="source-label">{source.label}</span>
          <span
            className={`source-badge ${
              source.type === "internal" ? "internal" : "external"
            }`}
          >
            {source.type === "internal" ? "🗄️ Database" : "🌐 Web"}
          </span>
        </div>
        {source.price && (
          <div className="source-price-row">
            <span className="source-price">{source.price}</span>
            {source.price_date && source.price_date !== "-" && (
              <span className="source-date">· {formatDateId(source.price_date)}</span>
            )}
          </div>
        )}
        {source.snippet && source.type === "external" && (
          <div className="source-snippet">{truncate(source.snippet, 120)}</div>
        )}
      </div>
      {source.url && <span className="external-icon">↗</span>}
    </Wrapper>
  );
}

function formatDateId(iso) {
  if (!iso || iso === "-") return "";
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
