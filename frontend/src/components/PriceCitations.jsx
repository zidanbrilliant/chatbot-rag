import React, { useState } from "react";

/**
 * PriceCitations — renders the source list at the bottom of an NL response.
 *
 * Each source has a stable ID [1], [2], ... referenced inline in the LLM answer.
 * Shows source label, price, and clickable URL for external sources.
 *
 * By default shows the top 3 most relevant sources. If there are more,
 * a "Lihat N lainnya" expander reveals them.
 *
 * Also renders a comparison card when market_prices are present,
 * showing internal DB price vs marketplace prices side-by-side.
 */
const VISIBLE_LIMIT = 3;

export default function PriceCitations({ sources, intent, marketPrices }) {
  const [showAll, setShowAll] = useState(false);
  if (!sources || sources.length === 0) return null;

  const isLowest = intent?.field_type === "low";
  const internalCount = sources.filter((s) => s.type === "internal").length;
  const externalCount = sources.filter((s) => s.type === "external").length;
  const marketplaceCount = sources.filter((s) => s.type === "marketplace").length;
  const showComparison = internalCount > 0 && marketplaceCount > 0;

  const visibleSources = showAll
    ? sources
    : sources.slice(0, VISIBLE_LIMIT);
  const hiddenCount = sources.length - visibleSources.length;

  return (
    <div className="price-citations-wrapper">
      {showComparison && marketPrices && marketPrices.length > 0 && (
        <ComparisonCard sources={sources} marketPrices={marketPrices} />
      )}

      {intent && (
        <div className="citations-header">
          <span className="citations-icon">📚</span>
          <strong>Sumber ({sources.length})</strong>
          {isLowest && <span className="lowest-badge">🏆 Termurah</span>}
          {internalCount > 0 && (
            <span className="source-stat">🗄️ {internalCount} database</span>
          )}
          {marketplaceCount > 0 && (
            <span className="source-stat">🛒 {marketplaceCount} marketplace</span>
          )}
          {externalCount > 0 && (
            <span className="source-stat">🌐 {externalCount} web</span>
          )}
        </div>
      )}

      <div className="sources-list">
        {visibleSources.map((s, idx) => (
          <SourceCard
            key={s.id}
            source={s}
            isCheapest={isLowest && idx === 0}
          />
        ))}
        {hiddenCount > 0 && (
          <button
            type="button"
            className="show-more-btn"
            onClick={() => setShowAll(true)}
          >
            ▼ Lihat {hiddenCount} sumber lainnya
          </button>
        )}
        {showAll && hiddenCount > 0 && (
          <button
            type="button"
            className="show-more-btn"
            onClick={() => setShowAll(false)}
          >
            ▲ Sembunyikan
          </button>
        )}
      </div>
    </div>
  );
}

function ComparisonCard({ sources, marketPrices }) {
  const internalSrc = sources.find((s) => s.type === "internal");
  if (!internalSrc) return null;

  const internalPrice = parsePrice(internalSrc.price);
  const cheapestMarket = marketPrices
    .filter((m) => m.price && m.price > 0)
    .sort((a, b) => a.price - b.price)[0];

  if (!internalPrice || !cheapestMarket) return null;

  const diff = internalPrice - cheapestMarket.price;
  const diffPct = internalPrice > 0
    ? Math.round((Math.abs(diff) / internalPrice) * 100)
    : 0;
  const isMarketCheaper = diff > 0;

  return (
    <div className="comparison-card">
      <div className="comparison-header">
        <span className="comparison-icon">📊</span>
        <strong>Perbandingan Harga</strong>
      </div>
      <div className="comparison-rows">
        <div className="comparison-row internal">
          <span className="comp-label">🗄️ Database</span>
          <span className="comp-value">{internalSrc.price}</span>
        </div>
        {marketPrices.slice(0, 3).map((mp, i) => {
          const isCheapest = i === 0;
          return (
            <a
              key={i}
              href={mp.url || "#"}
              target="_blank"
              rel="noreferrer"
              className={`comparison-row marketplace ${isCheapest ? "cheapest" : ""}`}
            >
              <span className="comp-label">
                🛒 {labelForMarketplace(mp.marketplace)}
                {mp.is_cached && <span className="cached-tag">cached</span>}
              </span>
              <span className="comp-value">
                {formatRupiah(mp.price, mp.currency)}
              </span>
              {isCheapest && cheapestMarket && (
                <span className="external-icon">↗</span>
              )}
            </a>
          );
        })}
      </div>
      {diff !== 0 && (
        <div className="comparison-footer">
          {isMarketCheaper ? (
            <span className="comp-diff cheaper">
              ▼ Lebih murah{" "}
              {formatRupiah(Math.abs(diff), cheapestMarket.currency)} ({diffPct}%)
            </span>
          ) : (
            <span className="comp-diff expensive">
              ▲ Lebih mahal{" "}
              {formatRupiah(Math.abs(diff), cheapestMarket.currency)} ({diffPct}%)
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function SourceCard({ source, isCheapest }) {
  const Wrapper = source.url ? "a" : "div";
  const wrapperProps = source.url
    ? { href: source.url, target: "_blank", rel: "noreferrer" }
    : {};

  const badgeLabel =
    source.type === "internal"
      ? "🗄️ Database"
      : source.type === "marketplace"
      ? `🛒 ${labelForMarketplace(source.marketplace) || "Marketplace"}`
      : "🌐 Web";

  return (
    <Wrapper
      {...wrapperProps}
      className={`source-card source-${source.type} ${
        source.url ? "clickable" : ""
      } ${isCheapest ? "cheapest" : ""} ${
        source.is_stale ? "stale" : ""
      }`}
    >
      <span className="source-marker">[{source.id}]</span>
      <div className="source-content">
        <div className="source-label-row">
          <span className="source-label">{source.label}</span>
          <span
            className={`source-badge ${source.type}`}
          >
            {badgeLabel}
          </span>
          {isCheapest && <span className="cheapest-badge">🏆 Termurah</span>}
          {source.is_stale && (
            <span className="stale-badge" title={`Data ${source.age_days || ">30"} hari yang lalu`}>
              ⚠️ Data lama
            </span>
          )}
        </div>
        {source.price && (
          <div className="source-price-row">
            <span className={`source-price ${isCheapest ? "cheapest-price" : ""}`}>
              {source.price}
            </span>
            {source.price_date && source.price_date !== "-" && (
              <span className="source-date">· {formatDateId(source.price_date)}</span>
            )}
            {source.price_date && source.price_date !== "-" && (
              <FreshnessBadge
                isoDate={source.price_date}
                sourceType={source.type}
              />
            )}
          </div>
        )}
        {source.snippet && (source.type === "external" || source.type === "marketplace") && (
          <div className="source-snippet">{truncate(source.snippet, 120)}</div>
        )}
      </div>
      {source.url && <span className="external-icon">↗</span>}
    </Wrapper>
  );
}

function FreshnessBadge({ isoDate, sourceType }) {
  const days = daysSince(isoDate);
  if (days === null) return null;
  let label = "";
  let cls = "freshness-fresh";
  if (days === 0) {
    label = "hari ini";
  } else if (days === 1) {
    label = "kemarin";
  } else if (days < 7) {
    label = `${days} hari lalu`;
  } else if (days < 30) {
    label = `${days} hari lalu`;
    cls = "freshness-medium";
  } else {
    label = `${days} hari lalu`;
    cls = "freshness-stale";
  }
  return (
    <span className={`freshness-badge ${cls}`} title={`Diperbarui ${label}`}>
      🕐 {label}
    </span>
  );
}

function daysSince(isoDate) {
  if (!isoDate || isoDate === "-") return null;
  const d = new Date(isoDate);
  if (isNaN(d.getTime())) return null;
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  return Math.max(0, Math.floor(diffMs / (1000 * 60 * 60 * 24)));
}

function labelForMarketplace(id) {
  const labels = {
    tokopedia: "Tokopedia",
    shopee: "Shopee",
    lazada: "Lazada",
    bukalapak: "Bukalapak",
    bhinneka: "Bhinneka",
    blibli: "Blibli",
    brand_store: "Official Store",
  };
  return labels[id] || (id ? id.charAt(0).toUpperCase() + id.slice(1) : "");
}

function formatRupiah(value, currency) {
  if (value == null || isNaN(value)) return "-";
  const num = Math.round(value);
  const formatted = "Rp " + num.toLocaleString("id-ID");
  if (currency && currency !== "IDR") {
    return `${currency} ${num.toLocaleString("id-ID")}`;
  }
  return formatted;
}

function parsePrice(priceStr) {
  if (!priceStr) return 0;
  const match = priceStr.match(/[\d,]+/);
  if (!match) return 0;
  return parseInt(match[0].replace(/,/g, ""), 10) || 0;
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
  return text.length > n ? text.substring(0, n) + "…" : "";
}
