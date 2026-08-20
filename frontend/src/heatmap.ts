// Holdings heatmap: one tile per symbol, size proportional to market value,
// colour by unrealised profit. Tiles flash green or red when the price ticks.
// A neutral cash tile completes the picture, so tile sizes read as shares of
// the whole portfolio, not just of the invested part.

import type { Holding } from "./api";

const FLASH_MS = 600;
// Its own namespace, so a real ticker named CASH could never collide.
const CASH_KEY = "·cash·";

export class Heatmap {
  private host: HTMLElement;
  private tiles = new Map<string, HTMLElement>();

  constructor(host: HTMLElement) {
    this.host = host;
    host.classList.add("heatmap");
  }

  render(
    holdings: Holding[],
    priceDirections: Record<string, "up" | "down" | "same">,
    cash = 0,
  ): void {
    const symbols = new Set(holdings.map((h) => h.symbol));
    if (holdings.length > 0) symbols.add(CASH_KEY);

    for (const [symbol, el] of this.tiles) {
      if (!symbols.has(symbol)) {
        el.remove();
        this.tiles.delete(symbol);
      }
    }

    if (holdings.length === 0) {
      this.host.dataset.empty = "true";
      return;
    }
    delete this.host.dataset.empty;

    // Short positions carry a negative market value; size tiles by exposure.
    const totalValue = holdings.reduce((s, h) => s + Math.abs(h.market_value), 0) + cash;

    for (const h of holdings) {
      const share = totalValue > 0 ? Math.abs(h.market_value) / totalValue : 1 / holdings.length;
      let tile = this.tiles.get(h.symbol);
      if (!tile) {
        tile = this.createTile(h.symbol);
        this.host.append(tile);
        this.tiles.set(h.symbol, tile);
      }
      tile.style.flexGrow = String(Math.max(0.05, share));
      tile.dataset.pnl = h.unrealized_pnl >= 0 ? "up" : "down";
      tile.querySelector(".heatmap-ticker")!.textContent = h.quantity < 0 ? `${h.symbol} (short)` : h.symbol;
      tile.querySelector(".heatmap-value")!.textContent = formatMoney(Math.abs(h.market_value));

      const dir = priceDirections[h.symbol];
      if (dir === "up" || dir === "down") flash(tile, dir);
    }

    let cashTile = this.tiles.get(CASH_KEY);
    if (!cashTile) {
      cashTile = this.createTile("Cash");
      cashTile.dataset.pnl = "cash";
      this.host.append(cashTile);
      this.tiles.set(CASH_KEY, cashTile);
    }
    cashTile.style.flexGrow = String(Math.max(0.05, totalValue > 0 ? cash / totalValue : 0));
    cashTile.querySelector(".heatmap-value")!.textContent = formatMoney(cash);
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
