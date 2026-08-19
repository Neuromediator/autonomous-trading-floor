// The per-trader activity log. Rows come from the backend already coloured by
// type (the same custom-tracing colours as the Gradio dashboard). Long messages
// are truncated to one line; hovering shows the full text, clicking a row
// toggles it open. The log re-renders on every poll, so expanded rows are
// remembered by key across renders.

import type { LogRow } from "./api";

export class LogView {
  private host: HTMLElement;
  private expanded = new Set<string>();

  constructor(host: HTMLElement) {
    this.host = host;
    host.classList.add("log");
  }

  render(rows: LogRow[]): void {
    // Only stick to the bottom if the user was already there; don't yank the
    // scroll away from a row they are reading.
    const stickToBottom =
      this.host.scrollTop + this.host.clientHeight >= this.host.scrollHeight - 8;

    this.host.innerHTML = "";
    if (rows.length === 0) {
      const empty = document.createElement("div");
      empty.className = "log-empty";
      empty.textContent = "Waiting for activity";
      this.host.append(empty);
      return;
    }
    for (const row of rows) {
      const key = `${row.datetime}|${row.type}|${row.message}`;
      const el = document.createElement("div");
      el.className = "log-row";
      el.classList.toggle("expanded", this.expanded.has(key));
      el.title = row.message;
      el.addEventListener("click", () => {
        if (this.expanded.has(key)) this.expanded.delete(key);
        else this.expanded.add(key);
        el.classList.toggle("expanded");
      });

      const time = document.createElement("span");
      time.className = "log-time";
      time.textContent = timeOf(row.datetime);

      const type = document.createElement("span");
      type.className = "log-type";
      type.style.color = row.color;
      type.textContent = row.type;

      const text = document.createElement("span");
      text.className = "log-text";
      text.textContent = row.message;

      el.append(time, type, text);
      this.host.append(el);
    }
    if (stickToBottom) this.host.scrollTop = this.host.scrollHeight;
  }
}

function timeOf(stamp: string): string {
  // Stored as "YYYY-MM-DD HH:MM:SS"; show just the time.
  const parts = stamp.split(" ");
  return parts.length > 1 ? parts[1] : stamp;
}
