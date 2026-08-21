// Holdings heatmap: one tile per symbol, size proportional to market value,
// colour by unrealised profit. Tiles flash green or red when the price ticks.
// A neutral cash tile completes the picture, so tile sizes read as shares of
// the whole portfolio, not just of the invested part. Positions are ranked by
// exposure and a tail of three or more is merged into one tile, because a panel
// only fits so many tiles before the sizes stop meaning anything; clicking that
// tile unfolds the rest.

import type { Holding } from "./api";

const FLASH_MS = 600;
// Their own namespace, so a real ticker named CASH could never collide.
const CASH_KEY = "·cash·";
const REST_KEY = "·rest·";
// A panel fits about ten tiles on one row before the ticker stops being
// readable and tile sizes all collapse to the minimum. Beyond that the
// smallest positions are merged into a single tile.
const MAX_HOLDING_TILES = 8;

export class Heatmap {
  private host: HTMLElement;
  private tiles = new Map<string, HTMLElement>();
  private showAll = false;
  /** Last render's inputs, so the merge tile can redraw on click. */
  private last: [Holding[], Record<string, "up" | "down" | "same">, number] | null = null;

  constructor(host: HTMLElement) {
    this.host = host;
    host.classList.add("heatmap");
  }

  render(
    holdings: Holding[],
    priceDirections: Record<string, "up" | "down" | "same">,
    cash = 0,
  ): void {
    if (holdings.length === 0) {
      for (const [key, el] of this.tiles) {
        el.remove();
        this.tiles.delete(key);
      }
      this.host.dataset.empty = "true";
      return;
    }
    delete this.host.dataset.empty;

    // Biggest exposure first, so the panel reads top-down by conviction.
    const ranked = [...holdings].sort(
      (a, b) => Math.abs(b.market_value) - Math.abs(a.market_value),
    );
    this.last = [holdings, priceDirections, cash];
    // Merging a single position saves no room — the tile costs what the ticker
    // would — so only fold a tail of two or more, and let a click unfold it.
    const tail = ranked.length - MAX_HOLDING_TILES;
    const foldable = tail >= 2 && !this.showAll;
    const shown = foldable ? ranked.slice(0, MAX_HOLDING_TILES) : ranked;
    const merged = foldable ? ranked.slice(MAX_HOLDING_TILES) : [];

    const live = new Set(shown.map((h) => h.symbol));
    live.add(CASH_KEY);
    if (merged.length > 0 || this.showAll) live.add(REST_KEY);
    for (const [key, el] of this.tiles) {
      if (!live.has(key)) {
        el.remove();
        this.tiles.delete(key);
      }
    }

    // Short positions carry a negative market value; size tiles by exposure.
    const totalValue = holdings.reduce((s, h) => s + Math.abs(h.market_value), 0) + cash;
    const shareOf = (value: number) => Math.max(0.05, totalValue > 0 ? value / totalValue : 0);
    const order: string[] = [];

    for (const h of shown) {
      const tile = this.tile(h.symbol);
      order.push(h.symbol);
      tile.style.flexGrow = String(shareOf(Math.abs(h.market_value)));
      tile.dataset.pnl = h.unrealized_pnl >= 0 ? "up" : "down";
      tile.querySelector(".heatmap-ticker")!.textContent = h.quantity < 0 ? `${h.symbol} (short)` : h.symbol;
      tile.querySelector(".heatmap-value")!.textContent = formatMoney(Math.abs(h.market_value));
      tile.title =
        `${h.symbol}: ${h.quantity} shares at $${h.price.toFixed(2)} ` +
        `(avg cost $${h.avg_cost.toFixed(2)}), ` +
        `unrealised ${h.unrealized_pnl >= 0 ? "+" : "-"}$${Math.abs(h.unrealized_pnl).toFixed(2)}`;

      const dir = priceDirections[h.symbol];
      if (dir === "up" || dir === "down") flash(tile, dir);
    }

    if (merged.length > 0 || this.showAll) {
      const value = merged.reduce((s, h) => s + Math.abs(h.market_value), 0);
      const tile = this.tile(REST_KEY, "more");
      order.push(REST_KEY);
      tile.dataset.pnl = "rest";
      tile.style.flexGrow = String(shareOf(value));
      tile.querySelector(".heatmap-ticker")!.textContent = this.showAll
        ? "show less"
        : `+${merged.length} more`;
      tile.querySelector(".heatmap-value")!.textContent = this.showAll
        ? ""
        : formatMoney(value);
      tile.title = this.showAll
        ? "Fold the smallest positions back into one tile"
        : merged.map((h) => `${h.symbol}: ${h.quantity} @ $${h.price.toFixed(2)}`).join("\n");
    }

    const cashTile = this.tile(CASH_KEY, "Cash");
    order.push(CASH_KEY);
    cashTile.dataset.pnl = "cash";
    cashTile.style.flexGrow = String(shareOf(cash));
    cashTile.querySelector(".heatmap-value")!.textContent = formatMoney(cash);
    cashTile.title = `Uninvested cash: $${cash.toFixed(2)}`;

    this.reorder(order);
  }

  /** The tile for a key, created on first use. */
  private tile(key: string, label = key): HTMLElement {
    let tile = this.tiles.get(key);
    if (!tile) {
      tile = this.createTile(label);
      if (key === REST_KEY) {
        tile.addEventListener("click", () => {
          this.showAll = !this.showAll;
          if (this.last) this.render(...this.last);
        });
      }
      this.host.append(tile);
      this.tiles.set(key, tile);
    }
    return tile;
  }

  /** Match DOM order to ranking, but only when it actually changed: re-appending
   *  a tile restarts its flash animation. */
  private reorder(order: string[]): void {
    const current = [...this.host.children];
    const wanted = order.map((key) => this.tiles.get(key)!);
    if (current.length === wanted.length && current.every((el, i) => el === wanted[i])) return;
    this.host.append(...wanted);
  }

  private createTile(symbol: string): HTMLElement {
    const tile = document.createElement("div");
    tile.className = "heatmap-tile";
    tile.innerHTML = `
      <span class="heatmap-ticker">${symbol}</span>
      <span class="heatmap-value"></span>
    `;
    return tile;
  }
}

function flash(tile: HTMLElement, dir: "up" | "down"): void {
  tile.classList.remove("flash-up", "flash-down");
  // Force reflow so the animation restarts when the direction repeats.
  void tile.offsetWidth;
  tile.classList.add(dir === "up" ? "flash-up" : "flash-down");
  setTimeout(() => tile.classList.remove("flash-up", "flash-down"), FLASH_MS);
}

function formatMoney(n: number): string {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(1)}k`;
  return `$${n.toFixed(0)}`;
}
