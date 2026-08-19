// A trader's recent trades, newest first. Mirrors the activity log's compact
// style. Each trade carries the agent's rationale: hover shows it as a tooltip,
// clicking the row unfolds it inline. Expanded rows are remembered by key
// because the list re-renders on every poll.

import type { Transaction } from "./api";

const MAX_ROWS = 12;

export class TransactionsView {
  private host: HTMLElement;
  private expanded = new Set<string>();

  constructor(host: HTMLElement) {
    this.host = host;
    host.classList.add("txns");
  }

  render(transactions: Transaction[]): void {
    this.host.innerHTML = "";
    if (transactions.length === 0) {
      const empty = document.createElement("div");
      empty.className = "txn-empty";
      empty.textContent = "No trades yet";
      this.host.append(empty);
      return;
    }
    for (const t of transactions.slice(-MAX_ROWS).reverse()) {
      const key = `${t.timestamp}|${t.symbol}|${t.quantity}`;
      const item = document.createElement("div");
      item.className = "txn-item";
      item.classList.toggle("expanded", this.expanded.has(key));
      item.title = t.rationale;
      item.addEventListener("click", () => {
        if (this.expanded.has(key)) this.expanded.delete(key);
        else this.expanded.add(key);
        item.classList.toggle("expanded");
      });

      const row = document.createElement("div");
      row.className = "txn-row";

      const date = document.createElement("span");
      date.className = "txn-date";
      date.textContent = dateOf(t.timestamp);

      const side = document.createElement("span");
      side.className = "txn-side";
      side.dataset.side = t.quantity >= 0 ? "buy" : "sell";
      side.textContent = t.quantity >= 0 ? "BUY" : "SELL";

      const detail = document.createElement("span");
      detail.className = "txn-detail";
      detail.textContent = `${Math.abs(t.quantity)} ${t.symbol} @ $${t.price.toFixed(2)}`;

      const rationale = document.createElement("div");
      rationale.className = "txn-rationale";
      rationale.textContent = t.rationale;

      row.append(date, side, detail);
      item.append(row, rationale);
      this.host.append(item);
    }
  }
}

function dateOf(stamp: string): string {
  // "YYYY-MM-DD HH:MM:SS" -> "MM-DD"
  const parts = stamp.split(" ")[0].split("-");
  return parts.length === 3 ? `${parts[1]}-${parts[2]}` : stamp;
}
